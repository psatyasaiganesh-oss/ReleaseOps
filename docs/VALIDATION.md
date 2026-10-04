# Validation record

Checked on **4 October 2026**. Results describe this source package, not a GitHub/cloud deployment.

| Check | Result | Scope |
|---|---|---|
| Application tests | Passed: 16 tests | HTTP/API behavior, authorization, cross-origin restrictions, validation, task/incident persistence, concurrent writes, metrics, consistent backups, probe deduplication |
| Local release rehearsal | Passed | Real Python process starts/restarts, failed readiness candidate, restoration of previous version, data preservation, outage-observation replay |
| Read-only smoke check | Passed | Readiness, version agreement, application API, dashboard, response policy headers, metrics |
| Browser interactions | Passed | Operator authentication, create/move task, report/investigate/resolve incident, real observation chart, navigation, lock editing |
| Responsive layout | Passed | Chromium at 1440px desktop and 390px mobile; no document-wide horizontal overflow; incident table scrolls within its panel |
| Browser JavaScript errors | None observed | Real Chromium/Playwright interaction run |
| Python/JavaScript syntax | Passed | Compileall and Node syntax checks |
| Bash syntax | Passed | Deploy, rollback, container rehearsal, and EC2 bootstrap |
| YAML | Parsed; job/Compose structure checked | Workflow and container configuration; this does not prove an actual Actions/Docker run |
| Docker deployment rehearsal | Not executed here | Docker is unavailable in the creation environment; included in CI and runnable on a Docker host |
| Terraform fmt/init/validate/plan | Not executed here | Terraform is unavailable here; fmt/init/validate are included in CI, plan needs your AWS account values |
| GitHub pipeline / GHCR publication | Not executed | Requires uploading the project to your repository |
| AWS resources / deployed cloud app | Not created | Infrastructure template and setup instructions are included |

The local rehearsal deliberately observes failures and reports a 60% pass rate for its five checks. That result is expected test evidence, not normal service availability. Example tickets are flagged; no successful cloud deployments or long-term availability numbers are fabricated.

## Repeat the checks

```bash
python3 -m unittest discover -s tests -v
python3 scripts/rehearse.py
python3 -m compileall -q releaseops scripts tests
node --check releaseops/static/app.js
bash -n scripts/deploy.sh scripts/rollback.sh scripts/container_rehearsal.sh infra/aws/bootstrap.sh
```

For smoke checking, run the app in another terminal, then `python3 scripts/smoke.py`.

For optional browser checks, use Node.js 22+ and install the development dependency:

```bash
npm install
npx playwright install chromium
node tests/browser.cjs
```

The test launches a private temporary API/database and shuts it down afterward. Screenshots go to `.local/browser`. A non-default Python executable can be supplied with the `PYTHON` environment variable. Creation-time browser checks used Playwright 1.62.1 and Chromium 153.

On a Docker-enabled host run `bash scripts/container_rehearsal.sh`. It uses a separate test namespace/volume and removes its own test data afterward. Infrastructure and delivery checks are configured in the supplied GitHub workflow but need a real workflow run to verify them.
