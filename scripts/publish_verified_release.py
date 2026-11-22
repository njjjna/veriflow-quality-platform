"""Publish v0.3.4 only after a successful, manually dispatched GitHub release run.

Uses the runner's short-lived GH_TOKEN, never a personal access token. Stores only
synthetic screenshots, test output, and commit provenance in the private repo.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TAG = 'v0.3.4'
REPO = 'njjjna/veriflow-quality-platform'


def command(*args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, text=True, **kwargs)


def output(*args):
    return command(*args, stdout=subprocess.PIPE).stdout.strip()


def main():
    if os.environ.get('GITHUB_REPOSITORY') != REPO:
        raise SystemExit('This publisher is scoped to the authorized VeriFlow repository.')
    if os.environ.get('GITHUB_EVENT_NAME') != 'workflow_dispatch' or os.environ.get('GITHUB_REF') != 'refs/heads/main':
        raise SystemExit('A manual release workflow on main is required.')
    source = output('git', 'rev-parse', 'HEAD')
    if source != os.environ['GITHUB_SHA']:
        raise SystemExit('Checkout and workflow source differ.')
    remote = output('git', 'ls-remote', 'origin', 'refs/heads/main').split()[0]
    if remote != source:
        raise SystemExit('main changed during testing; dispatch a run for the new source.')
    if output('git', 'ls-remote', '--tags', 'origin', 'refs/tags/' + TAG):
        raise SystemExit('Release tag already exists; refusing to overwrite it.')
    summaries = list((ROOT / 'test-artifacts/release-run').glob('*/run_summary.json'))
    if len(summaries) != 1:
        raise SystemExit('Exactly one fresh acceptance run is required.')
    run_dir = summaries[0].parent
    if json.loads(summaries[0].read_text()) != {'api':'passed', 'browser':'passed'}:
        raise SystemExit('Both independent suites must pass.')
    result = json.loads((run_dir / 'browser/browser_result.json').read_text())
    if result.get('status') != 'passed' or result.get('count') != 23 or len(result.get('cases', [])) != 23:
        raise SystemExit('The complete 23-case Chromium suite must pass.')
    screenshots = list((run_dir / 'browser').glob('*.png'))
    if len(screenshots) < 11:
        raise SystemExit('Expected Chromium evidence screenshots are missing.')

    evidence = ROOT / 'evidence/github-actions' / TAG
    shutil.copytree(run_dir, evidence, dirs_exist_ok=True)
    shutil.copytree(ROOT / 'test-artifacts/release-checks', evidence / 'regression', dirs_exist_ok=True)
    run_url = f"https://github.com/{REPO}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    metadata = {'tag':TAG, 'tested_source_commit':source, 'workflow_run':run_url,
                'browser_cases_passed':23, 'screenshots':len(screenshots),
                'api':'passed', 'browser':'passed', 'data':'synthetic only',
                'application_public_deployment':False}
    (evidence / 'run_metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    command('git', 'add', str(evidence.relative_to(ROOT)))
    tracked = subprocess.check_output(['git','ls-files','-z'], cwd=ROOT).decode().split('\0')
    manifest = ''.join(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() + '  ' + name + '\n'
                       for name in sorted(tracked) if name and name != 'SHA256SUMS.txt')
    (ROOT / 'SHA256SUMS.txt').write_text(manifest)
    command('git', 'add', 'SHA256SUMS.txt')
    command('git', '-c', 'user.name=github-actions[bot]',
            '-c', 'user.email=41898282+github-actions[bot]@users.noreply.github.com',
            'commit', '-m', 'docs: retain verified v0.3.4 browser UAT evidence')
    release_commit = output('git', 'rev-parse', 'HEAD')
    # This commit adds evidence and the manifest only. The tested app files do
    # not change between source and the release target.
    changed = output('git','diff','--name-only',source,release_commit).splitlines()
    if any(not (name.startswith('evidence/') or name == 'SHA256SUMS.txt') for name in changed):
        raise SystemExit('Release evidence commit unexpectedly changed application source.')
    command('git', 'push', 'origin', 'HEAD:main')

    dist = ROOT / 'dist'
    dist.mkdir(exist_ok=True)
    source_zip = dist / 'VeriFlow_v0.3.4_source_and_evidence.zip'
    with source_zip.open('wb') as stream:
        subprocess.run(['git','archive','--format=zip','--prefix=veriflow-enterprise/',release_commit],
                       cwd=ROOT, stdout=stream, check=True)
    evidence_zip = dist / 'VeriFlow_v0.3.4_browser_UAT_evidence.zip'
    with zipfile.ZipFile(evidence_zip,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(evidence.rglob('*')):
            if path.is_file(): archive.write(path,path.relative_to(evidence))
    provenance = dist / 'RELEASE_PROVENANCE.json'
    provenance.write_text(json.dumps({**metadata,'release_commit':release_commit},indent=2) + '\n')
    notes = (ROOT / 'docs/RELEASE_NOTES_v0.3.4.md').read_text()
    notes += f'\nTested source: `{source}`\n\nRelease commit (evidence only): `{release_commit}`\n\nVerification run: {run_url}\n'
    notes_file = dist / 'VeriFlow_v0.3.4_release_report.md'
    notes_file.write_text(notes)
    checksums = dist / 'SHA256SUMS_release.txt'
    files = [source_zip,evidence_zip,provenance,notes_file]
    checksums.write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in files))
    command('gh','release','create',TAG,'--repo',REPO,'--target',release_commit,
            '--title','VeriFlow v0.3.4 — verified cloud browser UAT',
            '--notes-file',str(notes_file),*[str(p) for p in files],str(checksums))
    release = json.loads(output('gh','release','view',TAG,'--repo',REPO,'--json','url,tagName,assets'))
    if len(release['assets']) != 5:
        raise SystemExit('Release created, but its asset count needs review.')
    with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a') as summary:
        summary.write(f"## Verified release\n\n[VeriFlow {TAG}]({release['url']})\n\n"
                      f"Chromium: 23/23. API: 15/15. Screenshots: {len(screenshots)}.\n\n"
                      f"Tested source: `{source}`\n\nRelease target: `{release_commit}`\n")
    print('Verified release:',release['url'])
    print('Assets:',', '.join(a['name'] for a in release['assets']))


if __name__ == '__main__': main()
