import importlib.util
from pathlib import Path
import unittest


def load(name):
    path=Path(__file__).resolve().parents[1]/'scripts'/(name+'.py')
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


class BetaReleaseTests(unittest.TestCase):
    def test_beta_refs_match_python_versions_and_lowercase_registry(self):
        metadata=load('release_metadata').metadata
        for ref in ('v0.3.0-beta.2','release/0.3.0-beta.2'):
            result=metadata('0.3.0b2',ref,'Owner/Project')
            self.assertEqual(result['version'],'0.3.0-beta.2')
            self.assertEqual(result['image'],'ghcr.io/owner/project')

    def test_stable_mismatched_or_injected_release_inputs_are_rejected(self):
        metadata=load('release_metadata').metadata
        for version,ref,repo in [('0.3.0','v0.3.0','owner/repo'),('0.3.0b2','v0.3.0-beta.3','owner/repo'),('0.3.0b2','v0.3.0-beta.2','owner/repo\ninjected=value')]:
            with self.assertRaises(ValueError):metadata(version,ref,repo)

    def test_completed_scan_findings_are_disclosed_not_suppressed(self):
        evaluate=load('beta_audit').evaluate
        report={'matches':[{'vulnerability':{'severity':'Critical'}},{'vulnerability':{'severity':'High'}}]}
        result=evaluate(report,1,'No usable sandbox')
        self.assertEqual(result['findings'],{'Critical':1,'High':1})
        self.assertFalse(result['vulnerability_gate_pass'])
        self.assertFalse(result['sandbox_gate_pass'])
        self.assertFalse(result['stable_release_approved'])

    def test_incomplete_scan_and_unexpected_browser_failure_block_beta(self):
        evaluate=load('beta_audit').evaluate
        with self.assertRaises(ValueError):evaluate({'error':'database failed'},0,'')
        with self.assertRaises(ValueError):evaluate({'matches':[]},1,'ModuleNotFoundError: broken dependency')

    def test_passing_checks_still_do_not_approve_a_stable_release(self):
        result=load('beta_audit').evaluate({'matches':[]},0,'sandbox passed')
        self.assertTrue(result['vulnerability_gate_pass'])
        self.assertTrue(result['sandbox_gate_pass'])
        self.assertFalse(result['stable_release_approved'])
