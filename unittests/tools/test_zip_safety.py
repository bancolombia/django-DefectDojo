import io
import zipfile
from unittest import TestCase
from unittest.mock import patch

from dojo.tools.utils import safe_open_zip, safe_read_all_zip


class TestZipSafety(TestCase):
    def make_zip(self, files, compression=zipfile.ZIP_DEFLATED):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", compression=compression) as zip_file:
            for name, contents in files.items():
                zip_file.writestr(name, contents)
        archive.seek(0)
        return archive

    def test_safe_read_all_zip_preserves_valid_archive_contents(self):
        archive = self.make_zip({"report.json": b'{"findings": []}'})

        self.assertEqual(
            safe_read_all_zip(archive),
            {"report.json": b'{"findings": []}'},
        )

    def test_safe_open_zip_rejects_too_many_members(self):
        archive = self.make_zip({"one.txt": b"1", "two.txt": b"2"})

        with patch("dojo.tools.utils.MAX_ZIP_MEMBERS", 1), self.assertRaisesRegex(ValueError, "members"):
            safe_open_zip(archive)

    def test_safe_open_zip_rejects_oversized_member(self):
        archive = self.make_zip({"large.txt": b"12345"}, compression=zipfile.ZIP_STORED)

        with patch("dojo.tools.utils.MAX_ZIP_MEMBER_SIZE", 4), self.assertRaisesRegex(ValueError, "per-member limit"):
            safe_open_zip(archive)

    def test_safe_open_zip_rejects_oversized_total(self):
        archive = self.make_zip({"one.txt": b"123", "two.txt": b"456"}, compression=zipfile.ZIP_STORED)

        with patch("dojo.tools.utils.MAX_ZIP_TOTAL_SIZE", 5), self.assertRaisesRegex(ValueError, "total uncompressed size"):
            safe_open_zip(archive)

    def test_safe_open_zip_rejects_excessive_compression_ratio(self):
        archive = self.make_zip({"compressed.txt": b"a" * 1024})

        with patch("dojo.tools.utils.MAX_ZIP_RATIO", 2), self.assertRaisesRegex(ValueError, "compression ratio"):
            safe_open_zip(archive)