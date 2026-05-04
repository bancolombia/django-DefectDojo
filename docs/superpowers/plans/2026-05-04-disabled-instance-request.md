# Disabled Instance Request — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an engagement-level dropdown action **"Disabled Instance Request"** that fires-and-forgets a POST to an internal API for engagements related to Tenable (either by `Tenable Scan` test with `ciclo_escaneo` tag, or by any Finding tagged with `tenable`).

**Architecture:** Clone the `Sync Scan Cycle` pattern already in `dojo/engagement/views.py:2291`. Three files modified, zero new models, zero migrations. The browser does GET → Django view → POST to `settings.PROVIDER_CORE_ENGINE` → JsonResponse → JS alert.

**Tech Stack:** Django 5.1, DRF, Tagulous (tags), Bootstrap dropdown (Bootstrap 3), FontAwesome 6, vanilla `fetch` for AJAX. Tests via `python manage.py test` inside Docker (`./run-unittest.sh -t <FQN>`).

**Spec:** `docs/superpowers/specs/2026-05-04-disabled-instance-request-design.md`

**Branch:** `feature/disabled_instance_request_tenable` (already created)

---

## File Structure

| File | Action | Why |
|---|---|---|
| `unittests/test_disabled_instance_request.py` | Create | Tests for visibility flag and AJAX endpoint. Uses `dojo_testdata.json` fixture + dynamically-created `Test_Type("Tenable Scan")` since fixture only has `NESSUS Scan`. |
| `dojo/engagement/views.py` | Modify | Add `show_disabled_instance_request` flag in `ViewEngagement.get` (~line 515) and `ViewEngagement.post` (~line 604); append `disabled_instance_request` AJAX view + `_disabled_instance_request_logic` helper at the bottom (after `sync_scan_cycle`). |
| `dojo/engagement/urls.py` | Modify | Register URL `/engagement/<eid>/disabled_instance_request/`. |
| `dojo/templates/dojo/view_eng.html` | Modify | Insert `<li>` after the `Sync Scan Cycle` block; append JS function `disabledInstanceRequest` after `syncScanCycle`. |

---

## Pre-flight

Before starting Task 1, ensure:

- Working directory: `/Users/felipearredondo/dev/bancolombia/django-DefectDojo`
- Branch: `feature/disabled_instance_request_tenable` (run `git branch --show-current` to confirm)
- Docker stack ready: this fork runs everything in `docker compose`. If you have not initialized it for unit tests yet, run from project root:

  ```bash
  ./docker/setEnv.sh unit_tests
  docker compose build
  docker compose up -d postgres uwsgi
  ```

- Verify `Test_Type` model has unique constraint on `name` (it does — irrelevant if you skip pre-loading and create dynamically per test, which is what this plan does).

---

## Task 1: Test scaffolding

**Files:**
- Create: `unittests/test_disabled_instance_request.py`

- [ ] **Step 1: Create the test file with fixture + setUp**

```python
import json
from unittest.mock import patch

from django.urls import reverse
from rest_framework.authtoken.models import Token

from dojo.models import Engagement, Finding, Product, Test, Test_Type

from .dojo_test_case import DojoTestCase


class DisabledInstanceRequestTests(DojoTestCase):
    """Tests for the engagement-level Disabled Instance Request feature."""

    fixtures = ["dojo_testdata.json"]

    def setUp(self):
        super().setUp()
        # Force-login as admin (DojoTestCase.client is a Django test client).
        self.client.force_login(self._get_admin_user())
        # The fixture ships NESSUS Scan but not Tenable Scan; create it on demand.
        self.tenable_test_type, _ = Test_Type.objects.get_or_create(name="Tenable Scan")
        # Build a fresh product + engagement isolated from fixture data.
        self.product = Product.objects.create(
            name="DIR-test-product",
            description="dummy",
            prod_type_id=1,
        )
        self.engagement = Engagement.objects.create(
            name="dir-test-engagement",
            product=self.product,
            target_start="2026-01-01",
            target_end="2026-12-31",
        )
        self.view_url = reverse("view_engagement", args=[self.engagement.id])

    def _get_admin_user(self):
        from dojo.models import User
        return User.objects.get(username="admin")

    def _add_tenable_test(self, *, tags=None):
        """Create a Tenable Scan Test attached to self.engagement, optionally tagged."""
        test = Test.objects.create(
            engagement=self.engagement,
            scan_type="Tenable Scan",
            test_type=self.tenable_test_type,
            target_start="2026-01-01",
            target_end="2026-01-02",
        )
        if tags:
            test.tags = tags
            test.save()
        return test

    def _add_finding(self, *, test, tags=None):
        finding = Finding.objects.create(
            test=test,
            title="dir-test-finding",
            severity="High",
            description="dummy",
            mitigation="dummy",
            impact="dummy",
            reporter=self._get_admin_user(),
        )
        if tags:
            finding.tags = tags
            finding.save()
        return finding

    def test_setup_smoke(self):
        """Sanity check that setUp wired everything correctly."""
        self.assertEqual(Test_Type.objects.filter(name="Tenable Scan").count(), 1)
        self.assertIsNotNone(self.engagement.id)
```

- [ ] **Step 2: Run the smoke test, verify it passes**

```bash
./run-unittest.sh -t unittests.test_disabled_instance_request.DisabledInstanceRequestTests.test_setup_smoke
```

Expected: `Ran 1 test ... OK`. If it fails because of `prod_type_id=1`, inspect the fixture: `python3 -c "import json; d=json.load(open('dojo/fixtures/dojo_testdata.json')); print([r for r in d if r['model']=='dojo.product_type'][:3])"` — if id 1 is not present, change `prod_type_id` to a valid id from the fixture.

- [ ] **Step 3: Commit**

```bash
git add unittests/test_disabled_instance_request.py
git commit -m "test: scaffold disabled_instance_request test module"
```

---

## Task 2: Visibility flag — Tenable Scan + ciclo_escaneo path

**Files:**
- Modify: `unittests/test_disabled_instance_request.py`
- Modify: `dojo/engagement/views.py:515` (GET branch of `ViewEngagement`)
- Modify: `dojo/templates/dojo/view_eng.html` (around line 72, after `Sync Scan Cycle` `<li>`)

- [ ] **Step 1: Add the failing test**

Append to `unittests/test_disabled_instance_request.py`:

```python
    def test_button_visible_when_engagement_has_tenable_scan_test(self):
        """A Tenable Scan test tagged 'ciclo_escaneo' should reveal the action."""
        self._add_tenable_test(tags=["ciclo_escaneo"])

        response = self.client.get(self.view_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Disabled Instance Request")
```

- [ ] **Step 2: Run it, verify it fails**

```bash
./run-unittest.sh -t unittests.test_disabled_instance_request.DisabledInstanceRequestTests.test_button_visible_when_engagement_has_tenable_scan_test
```

Expected: FAIL. The string "Disabled Instance Request" is not in the rendered HTML.

- [ ] **Step 3: Add the visibility flag in `ViewEngagement.get`**

In `dojo/engagement/views.py`, locate the line currently reading:

```python
        has_ciclo_escaneo_test = eng.test_set.filter(tags__name="ciclo_escaneo").exclude(tags__name__iexact="transferred").exists()
```

(approximately line 515). Immediately AFTER that line, add:

```python
        has_tenable_test = (
            eng.test_set
               .filter(scan_type="Tenable Scan", tags__name="ciclo_escaneo")
               .exclude(tags__name__iexact="transferred")
               .exists()
        )
        has_tenable_finding = eng.test_set.filter(
            finding__tags__name__icontains="tenable",
        ).exists()
        show_disabled_instance_request = has_tenable_test or has_tenable_finding
```

Then in the `render(request, self.get_template(), { ... })` block of the same method (around line 542), find the line `"has_ciclo_escaneo_test": has_ciclo_escaneo_test,` and add immediately after it:

```python
                "show_disabled_instance_request": show_disabled_instance_request,
```

- [ ] **Step 4: Add the dropdown entry in `view_eng.html`**

Open `dojo/templates/dojo/view_eng.html`. Find the existing `Sync Scan Cycle` block:

```django
                                {% if has_ciclo_escaneo_test and "_hosts." not in eng.name %}
                                        <li role="presentation">
                                            <a rel="noopener noreferrer" href="#" onclick="syncScanCycle({{ eng.id }}); return false;">
                                            <i class="fa-solid fa-refresh"></i> Sync Scan Cycle
                                            </a>
                                        </li>
                                {% endif %}
```

Immediately after the closing `{% endif %}` of that block, insert:

```django
                                {% if show_disabled_instance_request %}
                                        <li role="presentation">
                                            <a rel="noopener noreferrer" href="#" onclick="disabledInstanceRequest({{ eng.id }}); return false;">
                                            <i class="fa-solid fa-ban"></i> Disabled Instance Request
                                            </a>
                                        </li>
                                {% endif %}
```

- [ ] **Step 5: Run the test, verify it passes**

```bash
./run-unittest.sh -t unittests.test_disabled_instance_request.DisabledInstanceRequestTests.test_button_visible_when_engagement_has_tenable_scan_test
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add unittests/test_disabled_instance_request.py dojo/engagement/views.py dojo/templates/dojo/view_eng.html
git commit -m "feat(engagement): show Disabled Instance Request for Tenable Scan + ciclo_escaneo"
```

---

## Task 3: Visibility flag — Finding-tagged path (OR branch)

**Files:**
- Modify: `unittests/test_disabled_instance_request.py`

- [ ] **Step 1: Add the failing test**

Append:

```python
    def test_button_visible_when_engagement_has_finding_with_tenable_tag(self):
        """A Finding whose tag contains 'tenable' (case-insensitive) reveals the action,
        even if the parent test is NOT a Tenable Scan."""
        # Use a non-Tenable test type that exists in the fixture so we don't accidentally
        # satisfy the first OR branch.
        nessus_type, _ = Test_Type.objects.get_or_create(name="NESSUS Scan")
        non_tenable_test = Test.objects.create(
            engagement=self.engagement,
            scan_type="NESSUS Scan",
            test_type=nessus_type,
            target_start="2026-01-01",
            target_end="2026-01-02",
        )
        self._add_finding(test=non_tenable_test, tags=["Tenable_io_finding"])

        response = self.client.get(self.view_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Disabled Instance Request")
```

- [ ] **Step 2: Run, verify it passes immediately**

```bash
./run-unittest.sh -t unittests.test_disabled_instance_request.DisabledInstanceRequestTests.test_button_visible_when_engagement_has_finding_with_tenable_tag
```

Expected: PASS. The implementation from Task 2 already covers this case via `has_tenable_finding`. If it FAILS, the most likely cause is that Finding tags use a separate Tagulous related_name; in that case change the filter in `views.py` from `finding__tags__name__icontains` to the correct path. To diagnose: `docker compose exec uwsgi python manage.py shell -c "from dojo.models import Finding; print(Finding._meta.get_field('tags'))"` and inspect the related_name.

- [ ] **Step 3: Commit**

```bash
git add unittests/test_disabled_instance_request.py
git commit -m "test: cover OR branch — finding tag containing 'tenable'"
```

---

## Task 4: Visibility flag — negative cases

**Files:**
- Modify: `unittests/test_disabled_instance_request.py`

- [ ] **Step 1: Add the failing tests**

Append:

```python
    def test_button_hidden_when_no_tenable_signal(self):
        """Engagement with non-Tenable test and no tenable-tagged findings → hidden."""
        nessus_type, _ = Test_Type.objects.get_or_create(name="NESSUS Scan")
        Test.objects.create(
            engagement=self.engagement,
            scan_type="NESSUS Scan",
            test_type=nessus_type,
            target_start="2026-01-01",
            target_end="2026-01-02",
        )

        response = self.client.get(self.view_url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Disabled Instance Request")

    def test_button_hidden_when_only_tenable_test_is_transferred(self):
        """Tenable test with `transferred` tag must be excluded from the OR-A branch."""
        self._add_tenable_test(tags=["ciclo_escaneo", "Transferred"])  # mixed-case to verify __iexact

        response = self.client.get(self.view_url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Disabled Instance Request")
```

- [ ] **Step 2: Run, verify both pass**

```bash
./run-unittest.sh -t unittests.test_disabled_instance_request.DisabledInstanceRequestTests
```

Expected: all 5 tests PASS.

- [ ] **Step 3: Mirror the flag in `ViewEngagement.post`**

The view also has a POST handler that re-renders the same template. Without mirroring, a POST to the engagement page would lose the flag.

In `dojo/engagement/views.py`, locate the SECOND occurrence of:

```python
        has_ciclo_escaneo_test = eng.test_set.filter(tags__name="ciclo_escaneo").exclude(tags__name__iexact="transferred").exists()
```

(approximately line 604 — inside `ViewEngagement.post`). Add the same three-statement block AFTER that line:

```python
        has_tenable_test = (
            eng.test_set
               .filter(scan_type="Tenable Scan", tags__name="ciclo_escaneo")
               .exclude(tags__name__iexact="transferred")
               .exists()
        )
        has_tenable_finding = eng.test_set.filter(
            finding__tags__name__icontains="tenable",
        ).exists()
        show_disabled_instance_request = has_tenable_test or has_tenable_finding
```

Then in the `render(...)` of that method (around line 631), after `"has_ciclo_escaneo_test": has_ciclo_escaneo_test,` add:

```python
                "show_disabled_instance_request": show_disabled_instance_request,
```

- [ ] **Step 4: Re-run the full suite to confirm POST handler still good**

```bash
./run-unittest.sh -t unittests.test_disabled_instance_request.DisabledInstanceRequestTests
```

Expected: all 5 tests still PASS (no regression).

- [ ] **Step 5: Commit**

```bash
git add unittests/test_disabled_instance_request.py dojo/engagement/views.py
git commit -m "feat(engagement): hide Disabled Instance Request when no tenable signal; mirror flag in POST"
```

---

## Task 5: AJAX endpoint — URL + login required

**Files:**
- Modify: `unittests/test_disabled_instance_request.py`
- Modify: `dojo/engagement/urls.py:17` (after `sync_ecr_scan_cycle`)
- Modify: `dojo/engagement/views.py` (append at end)

- [ ] **Step 1: Add the failing test**

Append:

```python
    def test_endpoint_requires_login(self):
        """Unauthenticated GET should redirect to login (302)."""
        self.client.logout()
        url = reverse("disabled_instance_request", args=[self.engagement.id])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.url)
```

- [ ] **Step 2: Run it, verify it fails**

```bash
./run-unittest.sh -t unittests.test_disabled_instance_request.DisabledInstanceRequestTests.test_endpoint_requires_login
```

Expected: FAIL with `NoReverseMatch: Reverse for 'disabled_instance_request' not found`.

- [ ] **Step 3: Register the URL**

Open `dojo/engagement/urls.py`. Find the existing `sync_ecr_scan_cycle` route (around line 17):

```python
    re_path(r"^engagement/(?P<eid>\d+)/sync_ecr/$", views.sync_scan_cycle,
        name="sync_ecr_scan_cycle"),
```

Immediately after it, add:

```python
    re_path(r"^engagement/(?P<eid>\d+)/disabled_instance_request/$",
        views.disabled_instance_request,
        name="disabled_instance_request"),
```

- [ ] **Step 4: Add the view stub**

Open `dojo/engagement/views.py`. Append at the very end of the file (after `_sync_scan_cycle_logic`):

```python


# TODO: ENDPOINT_TBD — replace with the actual API path once the contract is defined.
# Combined with settings.PROVIDER_CORE_ENGINE to form the final URL.
DISABLED_INSTANCE_REQUEST_PATH = "engine-backend/<TBD>/disabledInstanceRequest"


@login_required
def disabled_instance_request(request, eid):
    """AJAX view to request the disabling of a Tenable instance for the engagement."""
    engagement = get_object_or_404(Engagement, id=eid)
    try:
        ok = _disabled_instance_request_logic(engagement, request)
        if ok:
            return JsonResponse({
                "success": True,
                "message": "Disabled instance request sent successfully",
            })
        msg = "Disabled instance request failed"
        raise Exception(msg)
    except Exception as e:
        logger.exception(f"Error on disabled instance request for engagement {eid}")
        return JsonResponse(
            {"success": False, "error": f"Error on disabled instance request for engagement: {eid}, ex: {e}"},
            status=500,
        )


def _disabled_instance_request_logic(engagement, request):
    """Fire a POST to the external service to request disabling the Tenable instance."""
    logger.info(f"Disabled instance request for engagement: {engagement.id} - {engagement.name}")
    base_url = f"{settings.PROVIDER_CORE_ENGINE}{DISABLED_INSTANCE_REQUEST_PATH}"
    user_token = Token.objects.get(user=User.objects.get(username=settings.OPERATIVE_USER))
    headers = {"Authorization": user_token.key}
    # TODO: ENDPOINT_TBD — confirm the query-param key with the API contract.
    # Defaulting to `dnsname` to mirror the existing Tenable branch in _sync_scan_cycle_logic.
    params = {"dnsname": engagement.name}
    res = requests.post(base_url, params=params, headers=headers)
    return res.status_code == 200
```

Verify these imports already exist near the top of `dojo/engagement/views.py`:
- `from django.contrib.auth.decorators import login_required` (already present)
- `from django.http import JsonResponse` (already present)
- `from django.shortcuts import get_object_or_404` (already present)
- `from django.conf import settings` (already present)
- `import requests` (already present)
- `from rest_framework.authtoken.models import Token` (already present — used by `_sync_scan_cycle_logic`)
- `from dojo.models import Engagement, User` (User comes via `from django.contrib.auth.models import User` already imported)

If any are missing, add them under the existing import block at the top of the file.

- [ ] **Step 5: Run the login test, verify it passes**

```bash
./run-unittest.sh -t unittests.test_disabled_instance_request.DisabledInstanceRequestTests.test_endpoint_requires_login
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add unittests/test_disabled_instance_request.py dojo/engagement/urls.py dojo/engagement/views.py
git commit -m "feat(engagement): add disabled_instance_request URL and view skeleton"
```

---

## Task 6: AJAX endpoint — success path

**Files:**
- Modify: `unittests/test_disabled_instance_request.py`

- [ ] **Step 1: Add the failing test**

Append:

```python
    @patch("dojo.engagement.views.requests")
    def test_endpoint_returns_success_on_external_200(self, mock_requests):
        """When the external API returns 200, the view returns success JSON."""
        mock_response = mock_requests.post.return_value
        mock_response.status_code = 200

        url = reverse("disabled_instance_request", args=[self.engagement.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertTrue(body["success"])
        self.assertIn("successfully", body["message"])
        # Verify it actually called the external API with engagement.name as dnsname.
        mock_requests.post.assert_called_once()
        call_kwargs = mock_requests.post.call_args.kwargs
        self.assertEqual(call_kwargs["params"], {"dnsname": self.engagement.name})
        self.assertIn("Authorization", call_kwargs["headers"])
```

- [ ] **Step 2: Run, verify it passes**

```bash
./run-unittest.sh -t unittests.test_disabled_instance_request.DisabledInstanceRequestTests.test_endpoint_returns_success_on_external_200
```

Expected: PASS. The view skeleton from Task 5 already implements the success path; this test just exercises it end-to-end with a mock.

If the test FAILS with `Token.DoesNotExist` for the operative user: the fixture `dojo_testdata.json` does not provide a token for the user named in `settings.OPERATIVE_USER` (default `operative`). Fix by patching the token lookup:

```python
    @patch("dojo.engagement.views.Token")
    @patch("dojo.engagement.views.requests")
    def test_endpoint_returns_success_on_external_200(self, mock_requests, mock_token_cls):
        mock_token_cls.objects.get.return_value.key = "fake-operative-token"
        mock_response = mock_requests.post.return_value
        mock_response.status_code = 200
        # ...rest of test unchanged
```

- [ ] **Step 3: Commit**

```bash
git add unittests/test_disabled_instance_request.py
git commit -m "test: cover disabled_instance_request happy path with mocked external API"
```

---

## Task 7: AJAX endpoint — failure paths

**Files:**
- Modify: `unittests/test_disabled_instance_request.py`

- [ ] **Step 1: Add the failing tests**

Append:

```python
    @patch("dojo.engagement.views.Token")
    @patch("dojo.engagement.views.requests")
    def test_endpoint_returns_500_on_external_failure(self, mock_requests, mock_token_cls):
        """When the external API returns non-200, the view returns 500 JSON."""
        mock_token_cls.objects.get.return_value.key = "fake-operative-token"
        mock_response = mock_requests.post.return_value
        mock_response.status_code = 503

        url = reverse("disabled_instance_request", args=[self.engagement.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 500)
        body = json.loads(response.content)
        self.assertFalse(body["success"])
        self.assertIn("Error", body["error"])

    @patch("dojo.engagement.views.Token")
    @patch("dojo.engagement.views.requests")
    def test_endpoint_returns_500_on_network_exception(self, mock_requests, mock_token_cls):
        """When `requests.post` raises (e.g. ConnectionError), view returns 500 JSON."""
        mock_token_cls.objects.get.return_value.key = "fake-operative-token"
        mock_requests.post.side_effect = Exception("boom")

        url = reverse("disabled_instance_request", args=[self.engagement.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 500)
        body = json.loads(response.content)
        self.assertFalse(body["success"])
```

- [ ] **Step 2: Run, verify both pass**

```bash
./run-unittest.sh -t unittests.test_disabled_instance_request.DisabledInstanceRequestTests
```

Expected: all 8 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add unittests/test_disabled_instance_request.py
git commit -m "test: cover disabled_instance_request failure paths"
```

---

## Task 8: Frontend JS — AJAX dispatch

**Files:**
- Modify: `dojo/templates/dojo/view_eng.html` (around line 1140, end of `<script>` block)

JS is not unit-tested in this codebase; this task is a manual verification task.

- [ ] **Step 1: Append the JS function**

Open `dojo/templates/dojo/view_eng.html`. Find the existing `syncScanCycle` function (around line 1113). Immediately after the closing brace `}` of that function (around line 1140), and BEFORE the closing `</script>` tag, insert:

```javascript

        function disabledInstanceRequest(engagementId) {
            var btn = event.target.closest('a');
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Sending...';
            btn.style.opacity = '0.6';
            btn.style.pointerEvents = 'none';

            fetch(`/engagement/${engagementId}/disabled_instance_request/?_=${Date.now()}`)
            .then(response => response.json())
            .then(data => {
                btn.innerHTML = '<i class="fa-solid fa-ban"></i> Disabled Instance Request';
                btn.style.opacity = '1';
                btn.style.pointerEvents = 'auto';

                if (data.success) {
                    alert('Disabled instance request sent successfully');
                } else {
                    alert('Error: ' + (data.error || 'Unknown error'));
                }
            })
            .catch(error => {
                btn.innerHTML = '<i class="fa-solid fa-ban"></i> Disabled Instance Request';
                btn.style.opacity = '1';
                btn.style.pointerEvents = 'auto';
                alert('Error on request: ' + error);
                console.error('Error:', error);
            });
        }
```

- [ ] **Step 2: Re-run the full unit suite to confirm no regression**

```bash
./run-unittest.sh -t unittests.test_disabled_instance_request.DisabledInstanceRequestTests
```

Expected: all 8 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add dojo/templates/dojo/view_eng.html
git commit -m "feat(ui): wire disabledInstanceRequest JS handler"
```

---

## Task 9: Manual end-to-end verification

This task does not write code — it verifies the feature works in a browser. Follow the project's CLAUDE.md guidance: "For UI or frontend changes, start the dev server and use the feature in a browser before reporting the task as complete."

- [ ] **Step 1: Start the dev stack**

```bash
./docker/setEnv.sh dev
docker compose build
docker compose up -d
docker compose logs initializer | grep "Admin password:"
```

Wait for the initializer to finish (~3 minutes), then visit `http://localhost:8080`.

- [ ] **Step 2: Create an engagement that triggers the flag**

Log in as `admin` with the password printed above. Then either:

- **Path A:** Create a Product → Engagement, upload a `.nessus` or Tenable CSV via "Import Scan Results" with scan type `Tenable Scan`, then add the tag `ciclo_escaneo` to the resulting Test (Test → Edit → Tags).
- **Path B:** On any existing engagement that already has Findings, manually add a Finding tag containing `tenable` (e.g. `tenable_io`) via Findings → bulk edit → Add tag.

- [ ] **Step 3: Verify the dropdown entry**

Navigate to the engagement detail page. Click the right-side dropdown (`Description` panel header → bars icon). Confirm:

- ✅ "Disabled Instance Request" entry is visible with the `fa-ban` icon.
- ✅ Above it, the existing "Sync Scan Cycle" entry is unaffected.

- [ ] **Step 4: Verify the AJAX flow**

With the placeholder endpoint still in place, clicking will produce a 500 (because `<TBD>` resolves to a non-existent path). That is **expected** at this stage. The visible behavior should be:

1. Button text changes to "Sending…" with a spinner.
2. After ~a second, an `alert()` pops up reading "Error: Error on disabled instance request for engagement: …" — this confirms the full Browser → Django → external POST → JsonResponse → JS alert chain wired up correctly.
3. Button text restores to "Disabled Instance Request".

In a separate terminal, tail the logs to confirm the request reached Django:

```bash
docker compose logs -f --tail=50 uwsgi | grep "Disabled instance"
```

You should see the `INFO Disabled instance request for engagement: <id> - <name>` log line and the `ERROR ... Error on disabled instance request ...` exception trace.

- [ ] **Step 5: Negative case in the browser**

Visit an engagement that has no Tenable test and no tenable-tagged finding. Confirm the entry is **NOT present** in the dropdown.

- [ ] **Step 6: Commit a CHANGELOG / no-op, only if verifications above expose any fix**

If anything fails verification, fix it and commit. If everything passes, no commit is needed at this step.

---

## Final state

After all 9 tasks complete, the branch contains (in order):

1. `docs: add design spec for Disabled Instance Request feature` (already committed before plan execution)
2. `test: scaffold disabled_instance_request test module`
3. `feat(engagement): show Disabled Instance Request for Tenable Scan + ciclo_escaneo`
4. `test: cover OR branch — finding tag containing 'tenable'`
5. `feat(engagement): hide Disabled Instance Request when no tenable signal; mirror flag in POST`
6. `feat(engagement): add disabled_instance_request URL and view skeleton`
7. `test: cover disabled_instance_request happy path with mocked external API`
8. `test: cover disabled_instance_request failure paths`
9. `feat(ui): wire disabledInstanceRequest JS handler`

Test count delta: +8 tests in `unittests.test_disabled_instance_request`.

Files touched: 4 (`unittests/test_disabled_instance_request.py` created; `dojo/engagement/views.py`, `dojo/engagement/urls.py`, `dojo/templates/dojo/view_eng.html` modified).

When the user provides the final API contract:
1. Edit `DISABLED_INSTANCE_REQUEST_PATH` in `dojo/engagement/views.py` (search `# TODO: ENDPOINT_TBD`).
2. Edit `params = {"dnsname": engagement.name}` in `_disabled_instance_request_logic` if the contract uses a different key.
3. If the contract requires JSON body instead of query params, change `requests.post(base_url, params=params, headers=headers)` to `requests.post(base_url, json={...}, headers=headers)`.
4. No tests need to change — they mock the call.

When ready to PR, push the branch and open a PR against `trunk`.
