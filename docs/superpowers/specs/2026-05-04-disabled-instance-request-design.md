# Disabled Instance Request — Design Spec

- **Branch**: `feature/disabled_instance_request_tenable`
- **Date**: 2026-05-04
- **Status**: Approved (pending implementation)
- **Reference flow**: `Sync Scan Cycle` (ECR/Lambda/Tenable) — already in `dojo/engagement/views.py:2291`

## 1. Goal

Add a new entry **"Disabled Instance Request"** in the engagement-level dropdown (the same dropdown that already contains "Edit Engagement" and "Sync Scan Cycle"), so the user can fire-and-forget a request to an internal API that disables a Tenable instance associated with the engagement.

The entry must appear ONLY when the engagement is related to Tenable, signaled by either of:

- **(A)** The engagement has at least one `Test` with `scan_type == "Tenable Scan"` AND tag `ciclo_escaneo` AND no tag `transferred` (case-insensitive).
- **(B)** The engagement has at least one `Finding` whose tags contain the string `"tenable"` (case-insensitive).

Visibility logic = `A OR B`.

The action is fire-and-forget: the click triggers a backend AJAX call which proxies a `POST` to a configured external endpoint (`settings.PROVIDER_CORE_ENGINE` + path) and returns a success/error JSON. The frontend shows an `alert()` with the outcome. Nothing is persisted in the DB.

## 2. Non-goals

- No new model / migration.
- No new permission. The action is only gated by `@login_required` (per product decision: any authenticated user that can see the engagement page can fire it).
- Not exposed in API v2 (DRF). HTML view + AJAX only, mirroring `sync_scan_cycle`.
- Does not fix the existing `user_has_permission_or_403` inversion bug at `dojo/engagement/views.py:2298` — out of scope.
- Does not modify the Tenable parser.

## 3. Architecture

Three files modified, zero new files (other than this spec):

| File | Change |
|---|---|
| `dojo/engagement/views.py` | Add visibility flag in `ViewEngagement` GET + POST handlers, and add the AJAX view `disabled_instance_request` + helper `_disabled_instance_request_logic`. |
| `dojo/engagement/urls.py` | Register URL `/engagement/<eid>/disabled_instance_request/` named `disabled_instance_request`. |
| `dojo/templates/dojo/view_eng.html` | Add `<li>` entry in the engagement options dropdown + new JS function `disabledInstanceRequest`. |

### 3.1 Data flow

```
User clicks <li>Disabled Instance Request</li>
   → JS disabledInstanceRequest(eid) — fetch GET /engagement/<eid>/disabled_instance_request/
   → Django view disabled_instance_request(request, eid) — @login_required
   → _disabled_instance_request_logic(engagement) — POST to {PROVIDER_CORE_ENGINE}{ENDPOINT_PATH}
   → JsonResponse {success, message|error}
   → JS alert(...) and dropdown button restored
```

The HTTP method between browser and Django is **GET** (decision d-i: cloning the existing `sync_scan_cycle` pattern). The HTTP method between Django and the external API is **POST** (per business intent — non-idempotent action).

### 3.2 Visibility flag

In `ViewEngagement.get` (around `dojo/engagement/views.py:515`) and `ViewEngagement.post` (around line 604), compute and pass:

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

Pass `"show_disabled_instance_request": show_disabled_instance_request` to `render(...)` in both branches.

> **Performance note**: the second filter does a `LEFT JOIN` over Test → Finding → tags. Because we use `.exists()` Postgres returns at the first match, so the cost is O(first matching row). If profiling shows latency, the implementation phase may swap to a `Subquery` / `Exists()` annotation; this is a known optional optimization.

### 3.3 Backend view

```python
# dojo/engagement/views.py — appended after sync_scan_cycle helpers

# TODO: ENDPOINT_TBD — replace with the actual path once the contract is defined.
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

**Where to set the endpoint when the contract arrives**:

1. **Path of the external endpoint** → `dojo/engagement/views.py`, constant `DISABLED_INSTANCE_REQUEST_PATH` (search the file for `# TODO: ENDPOINT_TBD`). Replace the placeholder string with the real path. The full URL is built as `settings.PROVIDER_CORE_ENGINE + DISABLED_INSTANCE_REQUEST_PATH`, so do **not** include the host in the constant.
2. **Query-param key for the engagement name** → same file, inside `_disabled_instance_request_logic`, the line `params = {"dnsname": engagement.name}`. Rename the key if the API contract uses something other than `dnsname`.
3. **HTTP method or body shape** (if the API turns out to expect JSON body instead of query params): change the `requests.post(base_url, params=params, headers=headers)` line to `requests.post(base_url, json={...}, headers=headers)`. The rest of the flow does not need to change.

### 3.4 URL

```python
# dojo/engagement/urls.py — appended right after sync_ecr (currently line 17-18)
re_path(
    r"^engagement/(?P<eid>\d+)/disabled_instance_request/$",
    views.disabled_instance_request,
    name="disabled_instance_request",
),
```

### 3.5 Template

**Dropdown entry** in `dojo/templates/dojo/view_eng.html`, inserted after the `Sync Scan Cycle` `<li>` (around line 72):

```django
{% if show_disabled_instance_request %}
    <li role="presentation">
        <a rel="noopener noreferrer" href="#" onclick="disabledInstanceRequest({{ eng.id }}); return false;">
            <i class="fa-solid fa-ban"></i> Disabled Instance Request
        </a>
    </li>
{% endif %}
```

**JS function** appended after `syncScanCycle` (around line 1140), inside the existing `<script>` block:

```js
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

## 4. Error handling

- 5xx (or any non-200) from external API → `_disabled_instance_request_logic` returns `False` → view raises → catch returns `{"success": false, "error": "..."}` with HTTP 500.
- Network exception → `requests.post` raises → caught and logged with `logger.exception` → JSON error to client.
- No retry, no queue, no DB write — fire-and-forget by design.

## 5. Test plan

New tests in `unittests/test_disabled_instance_request.py` (or appended to an existing engagement test module if one already covers the view):

| # | Name | Scenario | Expected |
|---|---|---|---|
| 1 | `test_button_visible_when_engagement_has_tenable_scan_test` | Eng has Test (`scan_type="Tenable Scan"`, tag `ciclo_escaneo`) | view_eng renders `Disabled Instance Request` |
| 2 | `test_button_visible_when_engagement_has_finding_with_tenable_tag` | Eng has no Tenable test, but has Finding tagged with a string containing `tenable` (e.g. `tenable`, `Tenable`, `tenable_io`) — verifies the case-insensitive `__icontains` match | renders entry |
| 3 | `test_button_hidden_when_no_tenable_signal` | Eng with non-Tenable tests/findings | entry NOT rendered |
| 4 | `test_button_hidden_when_only_tenable_test_is_transferred` | Eng has a Tenable+ciclo_escaneo+transferred test, no other signal | entry NOT rendered |
| 5 | `test_endpoint_returns_success_on_external_200` | Mock `requests.post` → 200 | JSON `{success: true, message: ...}` |
| 6 | `test_endpoint_returns_error_on_external_failure` | Mock `requests.post` → 500 | HTTP 500, JSON `{success: false, error: ...}` |
| 7 | `test_endpoint_requires_login` | Unauthenticated GET | redirected to login (Django default) |

All tests run with `./run-unittest.sh -t unittests.test_disabled_instance_request`.

## 6. Open items the user owns

- **External endpoint path** → set `DISABLED_INSTANCE_REQUEST_PATH` in `dojo/engagement/views.py`.
- **Query-param key** for engagement name → confirm `dnsname` is correct, otherwise rename in `_disabled_instance_request_logic`.

These can be adjusted any time after merging without re-running the design phase.

## 7. Out of scope

- API v2 (DRF) exposure of the action.
- DB persistence / audit log of requests.
- Retry / dead-letter / Celery offloading.
- Permission gates beyond `@login_required`.
- Refactor of the existing `sync_scan_cycle` permission bug.
- Internationalization of the alert messages (matches current English alerts in `view_eng.html`).
