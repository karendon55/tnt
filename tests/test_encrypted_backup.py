"""
Tests del backup cifrado: round-trip pack→unpack, contraseña incorrecta,
formato corrupto y restauración a fichero.
"""
import os
import tempfile
import unittest
from pathlib import Path

from app.services.encrypted_backup import (
    DEFAULT_ITERS, MAGIC, pack, pack_file, restore_file, unpack,
)


class TestPackUnpack(unittest.TestCase):
    def test_round_trip(self):
        data = b"hola mundo " * 100
        blob = pack(data, "contraseña-segura", iters=10_000)
        self.assertTrue(blob.startswith(MAGIC))
        self.assertEqual(unpack(blob, "contraseña-segura"), data)

    def test_default_iters(self):
        # Solo verificamos que los iters por defecto pueden cifrar y descifrar.
        data = b"x" * 16
        blob = pack(data, "abc", iters=DEFAULT_ITERS)
        self.assertEqual(unpack(blob, "abc"), data)

    def test_wrong_password_raises(self):
        blob = pack(b"secreto", "buena", iters=10_000)
        with self.assertRaises(ValueError) as ctx:
            unpack(blob, "mala")
        self.assertIn("Contraseña incorrecta", str(ctx.exception))

    def test_empty_password_raises(self):
        with self.assertRaises(ValueError):
            pack(b"x", "", iters=10_000)

    def test_corrupt_magic_raises(self):
        with self.assertRaises(ValueError) as ctx:
            unpack(b"NOPE\nxxxxxxxxxxx", "x")
        self.assertIn("no parece un backup", str(ctx.exception))

    def test_truncated_raises(self):
        with self.assertRaises(ValueError):
            unpack(MAGIC + b"\x00" * 3, "x")

    def test_iters_out_of_range_raises(self):
        # iters = 0 debe rechazarse en unpack
        bad = MAGIC + b"\x00\x00\x00\x00" + b"\x00" * 16 + b"x"
        with self.assertRaises(ValueError):
            unpack(bad, "x")

    def test_different_calls_different_blobs(self):
        # La sal aleatoria garantiza blobs distintos para los mismos datos.
        a = pack(b"x", "p", iters=10_000)
        b = pack(b"x", "p", iters=10_000)
        self.assertNotEqual(a, b)


class TestPackFile(unittest.TestCase):
    def test_pack_file_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "src.bin"
            src.write_bytes(b"sqlite-fake-content" * 50)
            blob = pack_file(src, "x" * 8, iters=10_000)
            self.assertEqual(unpack(blob, "x" * 8), src.read_bytes())


class TestRestoreFile(unittest.TestCase):
    def test_restore_creates_backup_of_previous(self):
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d) / "tnt.db"
            dest.write_bytes(b"old-data")
            blob = pack(b"new-data", "p" * 8, iters=10_000)

            prev_path, sha = restore_file(blob, "p" * 8, dest)

            self.assertEqual(dest.read_bytes(), b"new-data")
            # Se generó un fichero .before-restore-XXXXXXXX con los datos viejos
            self.assertTrue(prev_path.exists())
            self.assertEqual(prev_path.read_bytes(), b"old-data")
            self.assertEqual(len(sha), 64)  # sha256 hex

    def test_restore_to_empty_destination(self):
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d) / "tnt.db"
            blob = pack(b"new-data", "p" * 8, iters=10_000)
            prev_path, _ = restore_file(blob, "p" * 8, dest)

            self.assertEqual(dest.read_bytes(), b"new-data")
            # Sin fichero previo: prev_path == dest (señal de que no hubo backup)
            self.assertEqual(prev_path, dest)

    def test_restore_with_bad_password_does_not_touch_dest(self):
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d) / "tnt.db"
            dest.write_bytes(b"original")
            blob = pack(b"new-data", "buena", iters=10_000)
            with self.assertRaises(ValueError):
                restore_file(blob, "mala", dest)
            # El fichero original sigue intacto
            self.assertEqual(dest.read_bytes(), b"original")
            # No se ha creado ningún fichero adicional
            self.assertEqual(sorted(os.listdir(d)), ["tnt.db"])


if __name__ == "__main__":
    unittest.main()
