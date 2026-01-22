# Django Micboard - Next Steps Checklist
## Post-Review Testing Phase

**Status:** Ready to Begin  
**Date:** January 21, 2026

---

## Phase 1: Service Startup ⏱️ (15 minutes)

### Step 1.1: Terminal 1 - Start ASGI Server
- [ ] Open new terminal
- [ ] Navigate to project: `cd /home/skuonen/django-micboard`
- [ ] Set environment variables (copy from QUICK_START.sh)
- [ ] Run: `uv run daphne -b 0.0.0.0 -p 8000 demo.asgi:application`
- [ ] Verify: "Listening on TCP address 0.0.0.0:8000"
- [ ] Keep terminal open

### Step 1.2: Terminal 2 - Start Device Polling
- [ ] Open new terminal
- [ ] Navigate to project: `cd /home/skuonen/django-micboard`
- [ ] Set shared key environment variable
- [ ] Run: `uv run python manage.py poll_devices`
- [ ] Verify: "Device polling started..."
- [ ] Keep terminal open

### Step 1.3: Terminal 3 - Run API Tests
- [ ] Open new terminal
- [ ] Navigate to project: `cd /home/skuonen/django-micboard`
- [ ] Set environment variables
- [ ] Run: `uv run python shure_api_test.py --no-ssl-verify`
- [ ] Check test results (expect HTTP 401 or successful auth)
- [ ] Review any error messages

---

## Phase 2: API Connectivity Testing ⏱️ (10 minutes)

### Step 2.1: Health Check
- [ ] From Terminal 3, note health check result
- [ ] If healthy: Proceed to Step 2.2
- [ ] If unhealthy: Check Shure API is running on localhost:10000

### Step 2.2: Device Retrieval
- [ ] Monitor Terminal 2 for device polling messages
- [ ] Check for device list output
- [ ] Verify count of devices retrieved
- [ ] If successful: Proceed to Phase 3
- [ ] If 401 errors: See troubleshooting guide

### Step 2.3: WebSocket Connection
- [ ] Use browser to test WebSocket (optional)
- [ ] Navigate to: http://localhost:8000
- [ ] Open browser console (F12)
- [ ] Watch for WebSocket connection in Network tab
- [ ] Verify ws://localhost:8000/ws/devices/ connects

---

## Phase 3: Authentication Verification ⏱️ (20 minutes)

### Step 3.1: If Getting 401 Errors

**Option A: Verify Shared Key**
```bash
# In Terminal 3, verify the key
echo $MICBOARD_SHURE_API_SHARED_KEY

# Verify it matches the one in Shure System API
cat /mnt/c/ProgramData/Shure/SystemAPI/Standalone/Security/sharedkey.txt
```
- [ ] Keys match exactly (no whitespace differences)
- [ ] No line endings or extra characters
- [ ] If different: Update environment variable

**Option B: Test Shure API Directly**
```bash
# Test with curl (from Terminal 3)
curl -k -H "x-api-key: $MICBOARD_SHURE_API_SHARED_KEY" \
  https://localhost:10000/api/v1/devices | python -m json.tool
```
- [ ] If successful (200 response): Shared key is correct
- [ ] If 401: Shure API rejects this shared key
- [ ] If connection error: Shure API not running

**Option C: Check Shure System API Logs**
- [ ] Navigate to: `C:\ProgramData\Shure\SystemAPI\Standalone\logs\`
- [ ] Look for authentication failures
- [ ] Check what authentication method is expected
- [ ] Verify with Shure documentation

### Step 3.2: If Authentication Succeeds

- [ ] Verify all tests in shure_api_test.py pass
- [ ] Check device list is populated
- [ ] Confirm Django models are being updated
- [ ] Monitor Terminal 2 for successful polling
- [ ] Proceed to Phase 4

---

## Phase 4: Database Verification ⏱️ (5 minutes)

### Step 4.1: Check Models Are Populated
```bash
# In a new Terminal 4, run Django shell
cd /home/skuonen/django-micboard
uv run python manage.py shell
```

```python
# Check if devices were polled
from micboard.models import Receiver, Transmitter
print(f"Receivers: {Receiver.objects.count()}")
print(f"Transmitters: {Transmitter.objects.count()}")

# Show first few
for rx in Receiver.objects.all()[:3]:
    print(f"  - {rx.name} (ID: {rx.external_id})")

# Exit
exit()
```
- [ ] Count matches expected number of devices
- [ ] Device names are populated correctly
- [ ] External IDs match Shure API format

---

## Phase 5: Admin Interface Check ⏱️ (5 minutes)

### Step 5.1: Access Django Admin
- [ ] Open browser: http://localhost:8000/admin
- [ ] Login with superuser (or create one if needed)
- [ ] Navigate to Micboard section
- [ ] Check "Receivers" - should show polled devices
- [ ] Check "Transmitters" - should show transmitter data
- [ ] Check "Real-Time Connections" - shows connection status

### Step 5.2: Verify Device Data
- [ ] Click on a receiver to see details
- [ ] Verify fields are populated:
  - [ ] Name
  - [ ] Model
  - [ ] Serial Number
  - [ ] IP Address
  - [ ] Online Status
- [ ] Check transmitter assignments
- [ ] Review channel data

---

## Phase 6: Real-Time Updates Testing ⏱️ (10 minutes)

### Step 6.1: Trigger Device Updates
- [ ] From Shure System UI, change a device setting
- [ ] Or simulate device state change
- [ ] Or manually trigger polling: `curl http://localhost:8000/api/devices/refresh`

### Step 6.2: Verify Update Flow
- [ ] Check Terminal 2 for polling messages
- [ ] Monitor Terminal 1 for WebSocket broadcasts
- [ ] Refresh admin interface - data should update
- [ ] Check browser console for WebSocket messages

### Step 6.3: WebSocket Message Verification
```javascript
// In browser console (if WebSocket connected)
console.log("WebSocket messages received");
```
- [ ] Messages flowing through WebSocket
- [ ] Data format is correct JSON
- [ ] Timestamps are current

---

## Phase 7: Performance Baseline ⏱️ (15 minutes)

### Step 7.1: Polling Performance
- [ ] Time a device poll operation
- [ ] Note response time from Shure API
- [ ] Record number of devices retrieved
- [ ] Calculate devices per second
- [ ] **Target:** < 2 seconds for full sync

### Step 7.2: Database Performance
- [ ] Query all receivers: `time ./manage.py shell -c "from micboard.models import Receiver; Receiver.objects.all()"`
- [ ] Query all transmitters similarly
- [ ] Check query response times
- [ ] **Target:** < 100ms for 1000+ records

### Step 7.3: WebSocket Performance
- [ ] Connect 5+ WebSocket clients simultaneously
- [ ] Monitor CPU and memory usage
- [ ] Verify all clients receive updates
- [ ] **Target:** No lag, smooth updates

---

## Phase 8: Error Handling & Edge Cases ⏱️ (20 minutes)

### Step 8.1: Simulate Network Issues
- [ ] Stop Shure API (simulate disconnect)
- [ ] Watch for error handling in Terminal 2
- [ ] Verify reconnection logic activates
- [ ] Restart Shure API
- [ ] Verify automatic recovery

### Step 8.2: Rate Limiting Tests
- [ ] Trigger rapid API requests
- [ ] Monitor for rate limit responses (429)
- [ ] Verify backoff strategy works
- [ ] Confirm retry logic engages

### Step 8.3: Data Consistency
- [ ] Poll multiple times rapidly
- [ ] Verify database remains consistent
- [ ] Check for duplicate entries
- [ ] Verify no data loss

---

## Phase 9: Integration Test Suite ⏱️ (10 minutes)

### Step 9.1: Run Full Test Suite Again
```bash
cd /home/skuonen/django-micboard
uv run pytest micboard/tests/ -v --tb=short
```
- [ ] All 72 tests still pass
- [ ] No regressions introduced
- [ ] Performance is acceptable

### Step 9.2: Test Coverage Report
```bash
uv run pytest micboard/tests/ --cov=micboard --cov-report=html
```
- [ ] Generate coverage report
- [ ] Review coverage percentages
- [ ] Identify untested code paths (if any)

---

## Phase 10: Documentation & Sign-Off ⏱️ (10 minutes)

### Step 10.1: Record Results
- [ ] Note successful integration points
- [ ] Document any workarounds needed
- [ ] List any issues encountered
- [ ] Record performance metrics

### Step 10.2: Create Testing Report
- [ ] Summarize Phase 1-9 results
- [ ] List tests passed
- [ ] Note any failures and resolutions
- [ ] Include timestamps and metrics

### Step 10.3: Next Steps
- [ ] Identify what to test next
- [ ] Plan production deployment
- [ ] Schedule additional testing
- [ ] Plan performance optimization

---

## Troubleshooting Guide

### Issue: HTTP 401 Unauthorized
**Likely Cause:** Shared key not valid with Shure API
**Solution:**
1. Verify shared key hasn't expired
2. Get new key from Shure System API
3. Test with curl first: `curl -k -H "x-api-key: KEY" https://localhost:10000/api/v1/devices`
4. Check Shure API logs for more info

### Issue: Connection Refused
**Likely Cause:** Shure API not running
**Solution:**
1. Start Shure System API on Windows
2. Verify it's listening on port 10000
3. Test: `curl -k https://localhost:10000/v1.0/swagger.json`
4. Check Windows firewall isn't blocking

### Issue: WebSocket Won't Connect
**Likely Cause:** Daphne server not started
**Solution:**
1. Check Terminal 1 is running daphne
2. Verify no port conflicts (8000)
3. Check browser console for errors
4. Try: `curl http://localhost:8000/`

### Issue: Device Data Not Updating
**Likely Cause:** Polling not running
**Solution:**
1. Check Terminal 2 is running
2. Verify polling cycle is working
3. Check logs for errors
4. Manually trigger: `uv run python manage.py poll_devices --manufacturer shure`

### Issue: Out of Memory Error
**Likely Cause:** Large device list or memory leak
**Solution:**
1. Check device count: `SELECT COUNT(*) FROM micboard_receiver;`
2. Monitor RAM usage during polling
3. Check for connection leaks in code
4. Consider pagination for large datasets

---

## Success Criteria

### Phase 1-2: Service Startup
- [ ] All three services running
- [ ] No error messages in logs
- [ ] Services respond to requests
- [ ] Expected output in terminals

### Phase 3: Authentication
- [ ] Device polling successful (no 401s)
- [ ] Shure API data received
- [ ] Django models populated
- [ ] Data looks reasonable

### Phase 4-6: Data Flow
- [ ] Devices visible in admin
- [ ] Real-time updates flowing
- [ ] WebSocket connections working
- [ ] Database consistent

### Phase 7-9: Quality
- [ ] Performance acceptable
- [ ] Error handling working
- [ ] All tests passing
- [ ] No data loss

### Phase 10: Documentation
- [ ] Testing report complete
- [ ] Issues documented
- [ ] Next steps identified
- [ ] Ready for production

---

## Estimated Timeline

| Phase | Time | Cumulative |
|-------|------|-----------|
| 1: Startup | 15m | 15m |
| 2: Connectivity | 10m | 25m |
| 3: Authentication | 20m | 45m |
| 4: Database | 5m | 50m |
| 5: Admin | 5m | 55m |
| 6: Real-Time | 10m | 65m |
| 7: Performance | 15m | 80m |
| 8: Error Cases | 20m | 100m |
| 9: Test Suite | 10m | 110m |
| 10: Documentation | 10m | 120m |
| **TOTAL** | **~2 hours** | **120m** |

---

## Sign-Off

- [ ] All phases completed
- [ ] Testing report created
- [ ] Issues documented and resolved
- [ ] Performance acceptable
- [ ] Ready for next phase (production deployment)

**Tester Name:** _______________  
**Date:** _______________  
**Status:** _______________

---

For questions or issues, refer to:
- PROJECT_STATUS_REPORT.md
- LOCAL_TESTING_REPORT.md
- TESTING_SESSION_SUMMARY.md
- Documentation in docs/
