"""Version parsing, ranges and detection from package pins."""
import json
import os
import tempfile
import unittest

from core import versions


class TestVersions(unittest.TestCase):
    def test_compare_and_ranges(self):
        self.assertGreater(versions.cmp('0.46.1', '0.46.0'), 0)
        self.assertLess(versions.cmp('0.46.0-alpha', '0.46.0'), 0)
        self.assertTrue(versions.satisfies('0.46.1', '>=0.46.0 <0.47.0'))
        self.assertFalse(versions.satisfies('0.47.0', '>=0.46.0 <0.47.0'))
        self.assertEqual(versions.minor('0.46.4'), '0.46')

    def _repo(self, props, csproj, package_json):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, 'backend', 'src', 'App'))
        os.makedirs(os.path.join(d, 'portal'))
        if props:
            open(os.path.join(d, 'backend', 'Directory.Build.props'), 'w').write(props)
        open(os.path.join(d, 'backend', 'src', 'App', 'App.csproj'), 'w').write(csproj)
        if package_json:
            json.dump(package_json, open(os.path.join(d, 'portal', 'package.json'), 'w'))
        return d

    def test_msbuild_property_and_frontend_first(self):
        d = self._repo('<Project><PropertyGroup><SheshaVersion>[0.46.4]</SheshaVersion></PropertyGroup></Project>',
                       '<Project><ItemGroup><PackageReference Include="Shesha.Core" Version="$(SheshaVersion)" /></ItemGroup></Project>',
                       {'dependencies': {'@shesha-io/reactjs': '^0.46.0'}})
        det = versions.detect_repo(d)
        self.assertEqual(det['backend'], '0.46.4')       # property resolved, brackets stripped
        self.assertEqual(det['frontend'], '0.46.0')      # range prefix stripped
        self.assertEqual(det['framework'], '0.46.0')     # the frontend package is the framework release version

    def test_backend_fallback(self):
        d = self._repo(None, '<Project><ItemGroup><PackageReference Include="Shesha.Framework" Version="0.43.38" /></ItemGroup></Project>', None)
        self.assertEqual(versions.detect_repo(d)['framework'], '0.43.38')


if __name__ == '__main__':
    unittest.main()
