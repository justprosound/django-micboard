# Shure System API: Network Interface GUID Configuration

## Critical Issue: Wrong NetworkInterfaceId GUID Breaks Discovery

### The Problem

The Shure System API uses **Service Location Protocol (SLP)** to discover wireless devices on the network. This discovery process sends SLP unicast packets to configured IP addresses via a specific network interface.

**If the `NetworkInterfaceId` GUID in `appsettings.Standalone.json5` is wrong, discovery fails silently.**

### Symptoms of Wrong GUID

- ✗ No devices discovered despite IPs being configured and reachable
- ✗ Firewall logs show outbound SLP packets but no device responses
- ✗ Shure Update Utility **can** discover devices (proves network is OK)
- ✗ Manual network tests (ping) work fine
- ✗ System API service runs without errors

### Root Cause

The System API config file specifies which network interface to use for discovery:

```json
{
  "Discovery": {
    "NetworkInterfaceId": "{77966E49-BC72-4072-B6EC-2E9D8FE0CE94}"
  }
}
```

This GUID must match **an actual network adapter on the system**. If the GUID doesn't correspond to any real adapter, or if it's the wrong adapter, SLP packets get sent to the wrong network interface and never reach the devices.

### Why This Happens

- System was configured with default GUID from a template
- Network adapter was changed/replaced without updating config
- VPN connection uses different adapter than expected
- Multiple network interfaces available; wrong one selected

### How to Fix It

#### Step 1: Identify Your Network Adapters

On Windows, run PowerShell as Administrator:

```powershell
Get-NetAdapter | Select-Object Name, InterfaceDescription, ifIndex, InterfaceGuid | Format-Table -AutoSize
```

This shows all network adapters with their GUIDs. Look for:
- The adapter connected to your device network (172.21.x.x in our case)
- VPN adapters (PANGP, Cisco AnyConnect, etc.)
- Ethernet adapters

**Example output:**
```
Name        InterfaceDescription                                  ifIndex InterfaceGuid
----        ---------------------                                  ------- --------------
Ethernet 2  PANGP Virtual Ethernet Adapter Secure                21      {A283C67D-499A-4B7E-B628-F74E8061FCE2}
Ethernet    Intel I219-V                                          6       {1FFCAF67-F652-4C77-962B-494EE9E605F4}
Wi-Fi       Intel AX211                                          18       {93463FD1-8ACB-4E47-87A0-7D3DE4E1EC7E}
```

#### Step 2: Verify the Correct Adapter Has Your Device Network Route

Check the routing table for your device network (e.g., 172.21.0.0/16):

```powershell
route print | grep "172.21"
```

Or more detailed:

```powershell
Get-NetRoute -DestinationPrefix "172.21.0.0/16" | Select-Object DestinationPrefix, NextHop, ifIndex, RouteMetric
```

**Look for:**
- DestinationPrefix: Your device network (172.21.0.0/16)
- ifIndex: Interface number (e.g., 21)
- This ifIndex should match the adapter you identified in Step 1

#### Step 3: Match ifIndex to GUID

From Step 1, find the adapter with the ifIndex from Step 2. Its InterfaceGuid is your correct GUID.

**In our example:**
- Route uses ifIndex 21
- ifIndex 21 is "Ethernet 2" (PANGP adapter)
- GUID is `{A283C67D-499A-4B7E-B628-F74E8061FCE2}`

#### Step 4: Update the Config File

1. Stop the Shure System API Service:
   ```powershell
   net stop "Shure System API Service - Standalone"
   ```

2. Edit the config file:
   ```
   C:\ProgramData\Shure\SystemAPI\Standalone\appsettings.Standalone.json5
   ```

3. Find the Discovery section and update NetworkInterfaceId:
   ```json
   "Discovery": {
     "NetworkInterfaceId": "{A283C67D-499A-4B7E-B628-F74E8061FCE2}"
   }
   ```

4. Save the file

5. Restart the service:
   ```powershell
   net start "Shure System API Service - Standalone"
   ```

#### Step 5: Verify Discovery Works

Run the monitoring script to see devices being discovered:

```bash
python scripts/shure_discovery_monitor.py
```

Wait 30-60 seconds. You should see:
```
[HH:MM:SS] 🆕 NEW DEVICE(S) DISCOVERED:
  ├─ ULXD4D @ 172.21.2.140
  │  State: ONLINE  Firmware: 2.7.6.0
```

### Why Does Device Discovery Fail Silently?

The Shure System API behaves like this:

1. **SLP Bind Fails**: If GUID is wrong, binding to network interface fails
2. **Service Continues**: API doesn't crash; it just can't send discovery packets
3. **No Errors**: Config is technically valid JSON; wrong GUID is just wrong data
4. **No Devices Found**: Since no discovery packets are sent, no responses come back
5. **Service Appears Healthy**: Health checks (GET /api/v1/devices) work fine; just returns empty list

This is why troubleshooting takes so long—there are no obvious error messages.

### Verification Steps

Before and after changing the GUID, verify with:

**Before (should fail or show 0 devices):**
```bash
python scripts/shure_api_health_check.py
```

**After (should show discovered devices):**
```bash
python scripts/shure_discovery_monitor.py
```

### Network Interface Types You Might See

- **Ethernet**: Physical network card (Intel I219-V, Realtek, etc.)
- **Wi-Fi**: Wireless adapter (Intel AX211, etc.)
- **PANGP**: Palo Alto Networks VPN adapter
- **vEthernet**: Hyper-V virtual switch adapter
- **OpenVPN/TAP**: VPN tunnel adapter
- **Cisco AnyConnect**: Cisco VPN adapter
- **Default Switch**: Hyper-V default switch

### Common Mistakes

| Mistake | Impact | Prevention |
|---------|--------|-----------|
| Using wrong adapter GUID | Discovery sends packets to wrong network | Verify adapter has route to device network |
| Copying GUID with/without braces | GUID won't match format | Use exact GUID from Get-NetAdapter |
| Restarting before fixing | Service won't discover devices | Fix config FIRST, then restart |
| Firewall blocking SLP | Discovery packets blocked | Allow UDP 8427 outbound from adapter |
| Multiple GUIDs in config | System doesn't know which to use | Only one NetworkInterfaceId per config |

### Related Firewall Rules

Once the GUID is correct, ensure firewall allows:

- **UDP 8427** (SLP - Service Location Protocol)
- **TCP 2202** (TPCI - Terminal Protocol Communication Interface)
- **UDP 57383** (SDT - Discovery Protocol)

Check with:
```powershell
Get-NetFirewallRule -DisplayName "*SLP*" -Direction Outbound | Get-NetFirewallPortFilter
```

### Additional Resources

- Shure System API Documentation: `https://shure.com/docs/system-api`
- Windows Routing: `route print` or `Get-NetRoute`
- Network Adapters: `Get-NetAdapter` or Device Manager
- Firewall Logs: Event Viewer → Windows Logs → Security

### Quick Reference Commands

```powershell
# List all adapters with GUIDs
Get-NetAdapter | Select-Object Name, ifIndex, InterfaceGuid

# Find device network route
Get-NetRoute -DestinationPrefix "172.21.0.0/16"

# Stop/start API service
net stop "Shure System API Service - Standalone"
net start "Shure System API Service - Standalone"

# Check API health
curl -k -H "x-api-key: $KEY" https://localhost:10000/api/v1/devices
```

---

**Last Updated:** January 21, 2026
**Status:** Critical Configuration Issue
**Complexity:** Medium - Requires understanding of network interfaces and Windows configuration
