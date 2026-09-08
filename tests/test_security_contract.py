"""Auditable distribution/security invariants across runtime source files."""
from pathlib import Path
import re
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SecurityContractTests(unittest.TestCase):
    def test_runtime_qml_has_no_whole_output_collectors(self):
        for path in [*ROOT.glob('*.qml'), *ROOT.joinpath('ui').glob('*.qml')]:
            with self.subTest(path=path.name):
                self.assertNotRegex(path.read_text(), r'\bStdioCollector\s*\{')

    def test_every_text_sink_declares_plaintext(self):
        # Same brace audit used in the review skill; all current labels are plain.
        for path in [*ROOT.glob('*.qml'), *ROOT.joinpath('ui').glob('*.qml')]:
            source = path.read_text()
            for match in re.finditer(r'\b(?:Text|Label|TextEdit|StyledText)\s*\{', source):
                offset, depth = match.end(), 1
                while offset < len(source) and depth:
                    depth += (source[offset] == '{') - (source[offset] == '}')
                    offset += 1
                with self.subTest(path=path.name, line=source[:match.start()].count('\n') + 1):
                    self.assertRegex(source[match.end():offset], r'textFormat:\s*Text\.PlainText')

    def test_preview_is_small_png_without_text_metadata(self):
        data = (ROOT / 'preview.png').read_bytes()
        self.assertLessEqual(len(data), 512 * 1024)
        self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n')
        offset = 8
        while offset < len(data):
            length = struct.unpack('>I', data[offset:offset + 4])[0]
            kind = data[offset + 4:offset + 8]
            self.assertNotIn(kind, (b'tEXt', b'iTXt', b'zTXt', b'eXIf'))
            offset += length + 12
        self.assertEqual(offset, len(data))

    def test_readme_documents_removal_and_backup_residue(self):
        source = (ROOT / 'README.md').read_text()
        self.assertIn('## Removing', source)
        self.assertIn('omarchy plugin remove filipharald.oma-mise', source)
        self.assertIn('Removing the monitor does not', source)

    def test_plugin_id_is_consistent_and_has_no_reverse_domain_prefix(self):
        manifest = (ROOT / 'manifest.json').read_text()
        panel = (ROOT / 'Panel.qml').read_text()
        readme = (ROOT / 'README.md').read_text()
        for source in (manifest, panel, readme):
            self.assertIn('filipharald.oma-mise', source)
            self.assertNotIn('io.github.', source)


if __name__ == '__main__':
    unittest.main()
