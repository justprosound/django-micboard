# Phase 2 Integration Resources - Developer Tooling

**Date:** January 22, 2026
**Status:** ✅ Ready for Integration

## Overview

These modules provide comprehensive support for integrating the service layer into existing django-micboard code and building new features.

---

## 📦 New Modules

### 1. `micboard/migration_utils.py` (300 lines)

**Purpose:** Help refactor existing view code to use services.

**Key Classes:**

#### `MigrationHelper`
Suggests appropriate services for code patterns:
```python
# Analyze code and get suggestions
patterns = MigrationHelper.find_business_logic_patterns(old_view_code)
for pattern in patterns:
    print(f"{pattern['pattern']} → {pattern['suggestion']}")

# Generate migration guide
guide = MigrationHelper.generate_migration_guide(old_code)
```

#### `CodeAnalyzer`
Analyzes view complexity and refactoring priority:
```python
# Calculate complexity score (0-100)
score = CodeAnalyzer.complexity_score(view_code)

# Get refactoring priority
priority = CodeAnalyzer.suggest_refactoring_priority(view_code)
# Returns: 'Low', 'Medium', 'High', or 'Critical'
```

#### `ViewMigrationExample`
Provides before/after examples:
```python
# See how to migrate views
old_pattern = ViewMigrationExample.old_view_pattern()
new_pattern = ViewMigrationExample.new_view_pattern()
```

**Usage Example:**
```python
from micboard.migration_utils import MigrationHelper, CodeAnalyzer

# Analyze view complexity
view_code = """
def receiver_list(request):
    receivers = Receiver.objects.filter(active=True)
    for r in receivers:
        # ... lots of logic ...
"""

priority = CodeAnalyzer.suggest_refactoring_priority(view_code)
# Output: 'High' or 'Critical'

# Get migration suggestions
patterns = MigrationHelper.find_business_logic_patterns(view_code)
# Output: List of improvement suggestions
```

---

### 2. `micboard/performance_tools.py` (350 lines)

**Purpose:** Analyze and optimize performance of services.

**Key Classes:**

#### `PerformanceReport`
Dataclass for storing performance metrics:
```python
@dataclass
class PerformanceReport:
    operation_name: str
    duration_ms: float
    query_count: int
    cache_hits: int
    cache_misses: int
    success: bool
```

#### `PerformanceAnalyzer`
Profile service operations:
```python
from micboard.performance_tools import PerformanceAnalyzer

# Profile a service method
with PerformanceAnalyzer.analyze("get_receivers") as report:
    receivers = DeviceService.get_active_receivers()

print(f"Duration: {report.duration_ms}ms")
print(f"Queries: {report.query_count}")
```

#### `BenchmarkRunner`
Run performance benchmarks:
```python
from micboard.performance_tools import BenchmarkRunner

# Benchmark a function
results = BenchmarkRunner.benchmark(
    DeviceService.get_active_receivers,
    iterations=100
)

print(f"Avg: {results['avg_ms']:.2f}ms")
print(f"Min: {results['min_ms']:.2f}ms")
print(f"Max: {results['max_ms']:.2f}ms")
```

#### `LoadTestSimulator`
Simulate concurrent load:
```python
# Simulate 100 concurrent requests
results = LoadTestSimulator.simulate_concurrent_requests(
    DeviceService.get_active_receivers,
    concurrent_count=100
)

print(f"Throughput: {results['throughput_per_second']} req/s")
print(f"Avg response: {results['avg_response_time_ms']}ms")
```

**Usage Examples:**

```python
# Find slow queries
slow_queries = PerformanceAnalyzer.get_slow_queries(threshold_ms=100)
for query in slow_queries:
    print(f"{query['sql'][:50]}... ({query['time_ms']}ms)")

# Compare two implementations
comparison = BenchmarkRunner.compare_implementations(
    old_service_method,
    new_service_method,
    iterations=50
)
print(f"Improvement: {comparison['improvement_percent']}")
```

---

### 3. `micboard/integration_patterns.py` (400 lines)

**Purpose:** Common ready-to-use patterns for typical use cases.

**Key Classes:**

#### `BulkOperationPattern`
Handle bulk operations efficiently:
```python
from micboard.integration_patterns import BulkOperationPattern

# Bulk sync device status
results = BulkOperationPattern.bulk_sync_device_status(
    devices=receivers,
    online=True
)
print(f"Synced: {results['synced']}, Failed: {results['failed']}")

# Bulk create assignments
results = BulkOperationPattern.bulk_create_assignments(
    user=user,
    devices=receivers,
    alert_enabled=True
)
```

#### `DashboardDataPattern`
Efficiently gather dashboard data:
```python
from micboard.integration_patterns import DashboardDataPattern

# Get complete overview
dashboard = DashboardDataPattern.get_dashboard_overview()
print(f"Online devices: {dashboard['device_stats']['online']}")
print(f"Low battery: {dashboard['device_stats']['low_battery']}")

# Get user-specific dashboard
user_dashboard = DashboardDataPattern.get_user_dashboard(user=request.user)
print(f"User's assignments: {user_dashboard['assignments_count']}")
```

#### `AlertingPattern`
Implement alerting logic:
```python
from micboard.integration_patterns import AlertingPattern

# Check what alerts need to be sent
alerts = AlertingPattern.check_alerts_needed()
# {'low_battery': [...], 'offline': [...], ...}

# Get alerts for specific user
user_alerts = AlertingPattern.get_alerts_for_user(user=request.user)
# {'low_battery': [device1, device2], 'offline': [...]}
```

#### `ReportingPattern`
Generate reports:
```python
from micboard.integration_patterns import ReportingPattern

# Generate device status report
report = ReportingPattern.generate_device_status_report()
print(report)

# Generate health report
health = ReportingPattern.generate_health_report()
print(health)
```

**Common Use Cases:**

1. **Dashboard Loading:**
   ```python
   dashboard = DashboardDataPattern.get_dashboard_overview()
   return JsonResponse(dashboard)
   ```

2. **Bulk Updates:**
   ```python
   results = BulkOperationPattern.bulk_sync_device_status(
       devices=selected_devices,
       online=True
   )
   messages.success(request, f"Updated {results['synced']} devices")
   ```

3. **User Alerts:**
   ```python
   user_alerts = AlertingPattern.get_alerts_for_user(user=request.user)
   if user_alerts['low_battery']:
       # Send alert notification
   ```

4. **Reports:**
   ```python
   report = ReportingPattern.generate_device_status_report()
   response = HttpResponse(report, content_type='text/plain')
   response['Content-Disposition'] = 'attachment; filename="report.txt"'
   return response
   ```

---

### 4. `micboard/cli_tools.py` (300 lines)

**Purpose:** Build management commands using services.

**Key Classes:**

#### `ServiceCommandMixin`
Helpers for management commands:
```python
from django.core.management.base import BaseCommand
from micboard.cli_tools import ServiceCommandMixin

class Command(ServiceCommandMixin, BaseCommand):
    def handle(self, *args, **options):
        self.print_section("Device Sync")
        self.print_success("Synced 10 devices")
        self.print_warning("2 errors")
        self.print_error("Failed to sync shure")
```

**Output Methods:**
- `print_section(title)` - Print section header
- `print_success(message)` - ✓ Green text
- `print_error(message)` - ✗ Red text
- `print_warning(message)` - ⚠ Yellow text
- `print_info(message)` - ℹ Blue text
- `print_table(rows, headers)` - Formatted table

#### Example Commands

```python
# Sync Devices Command
class Command(ServiceCommandMixin, BaseCommand):
    help = 'Sync devices from manufacturer APIs'

    def add_arguments(self, parser):
        parser.add_argument('--manufacturer', help='Specific manufacturer')

    def handle(self, *args, **options):
        manufacturer = options['manufacturer'] or 'shure'
        result = ManufacturerService.sync_devices_for_manufacturer(
            manufacturer_code=manufacturer
        )
        self.print_success(f"Synced {result['devices_synced']} devices")
```

#### `CommandHelper`
Utility functions for CLI:
```python
from micboard.cli_tools import CommandHelper

# Ask for confirmation
if CommandHelper.confirm_action("Sync all devices?"):
    # Proceed

# Show progress
for i in range(100):
    print(CommandHelper.progress_bar(i, 100))

# Get user choice
choice = CommandHelper.get_user_choice({
    'sync': 'Sync all devices',
    'report': 'Generate report',
    'health': 'Check health'
})
```

---

## 🎯 Integration Workflow

### Week 1: Assessment
```python
from micboard.migration_utils import CodeAnalyzer

# Analyze all views
for view in existing_views:
    priority = CodeAnalyzer.suggest_refactoring_priority(view_code)
    if priority in ['High', 'Critical']:
        # Schedule for refactoring
```

### Week 2: Migration
```python
from micboard.migration_utils import MigrationHelper

# Get specific suggestions
patterns = MigrationHelper.find_business_logic_patterns(old_view)
# Follow guide to refactor
```

### Week 3: Performance
```python
from micboard.performance_tools import BenchmarkRunner

# Compare old vs new implementations
results = BenchmarkRunner.compare_implementations(old, new)
# Verify improvement
```

### Week 4: Deployment
```python
from micboard.integration_patterns import DashboardDataPattern

# Use patterns in new views
dashboard = DashboardDataPattern.get_dashboard_overview()
```

---

## 📊 Quick Reference

### Migration Helper
```python
MigrationHelper.suggest_service_for_pattern(code)
MigrationHelper.find_business_logic_patterns(code)
MigrationHelper.generate_migration_guide(code)
```

### Performance Tools
```python
PerformanceAnalyzer.analyze(name)
BenchmarkRunner.benchmark(func, iterations=100)
BenchmarkRunner.compare_implementations(old, new)
LoadTestSimulator.simulate_concurrent_requests(func, concurrent_count=10)
```

### Integration Patterns
```python
BulkOperationPattern.bulk_sync_device_status(devices, online)
DashboardDataPattern.get_dashboard_overview()
AlertingPattern.check_alerts_needed()
ReportingPattern.generate_device_status_report()
```

### CLI Tools
```python
ServiceCommandMixin.print_section(title)
ServiceCommandMixin.print_success(message)
CommandHelper.confirm_action(question)
CommandHelper.progress_bar(current, total)
```

---

## 🚀 Next Steps

1. **Use migration_utils.py** to identify which views to refactor first
2. **Run benchmarks** with performance_tools.py to measure baseline
3. **Apply integration_patterns.py** patterns in new views
4. **Create management commands** with cli_tools.py
5. **Monitor performance** improvements with metrics

---

## 📚 Related Documentation

- [Phase 2 Integration Guide](./PHASE2_INTEGRATION_GUIDE.md)
- [Services Quick Reference](./services-quick-reference.md)
- [Enhancements Overview](./ENHANCEMENTS_PHASE_1.md)

---

**Status:** Production-ready tooling for Phase 2 integration
