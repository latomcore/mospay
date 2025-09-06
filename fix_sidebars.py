#!/usr/bin/env python3
"""
Script to fix sidebar navigation in all analytics templates
"""

import os

# Complete sidebar structure
COMPLETE_SIDEBAR = '''        <!-- Sidebar -->
        <ul class="navbar-nav bg-gradient-primary sidebar sidebar-dark accordion" id="accordionSidebar">

            <!-- Sidebar - Brand -->
            <a class="sidebar-brand d-flex align-items-center justify-content-center" href="{{ url_for('admin.dashboard') }}">
                <div class="sidebar-brand-icon rotate-n-15">
                    <i class="fas fa-credit-card"></i>
                </div>
                <div class="sidebar-brand-text mx-3">MosPay</div>
            </a>

            <!-- Divider -->
            <hr class="sidebar-divider my-0">

            <!-- Nav Item - Dashboard -->
            <li class="nav-item">
                <a class="nav-link" href="{{ url_for('admin.dashboard') }}">
                    <i class="fas fa-fw fa-tachometer-alt"></i>
                    <span>Dashboard</span></a>
            </li>

            <!-- Divider -->
            <hr class="sidebar-divider">

            <!-- Heading -->
            <div class="sidebar-heading">
                Management
            </div>

            <!-- Nav Item - Clients -->
            <li class="nav-item">
                <a class="nav-link" href="{{ url_for('admin.clients') }}">
                    <i class="fas fa-fw fa-users"></i>
                    <span>Clients</span></a>
            </li>

            <!-- Nav Item - Services -->
            <li class="nav-item">
                <a class="nav-link" href="{{ url_for('admin.services') }}">
                    <i class="fas fa-fw fa-cogs"></i>
                    <span>Services</span></a>
            </li>

            <!-- Nav Item - Transactions -->
            <li class="nav-item">
                <a class="nav-link" href="{{ url_for('admin.transactions') }}">
                    <i class="fas fa-fw fa-exchange-alt"></i>
                    <span>Transactions</span></a>
            </li>

            <!-- Nav Item - API Logs -->
            <li class="nav-item">
                <a class="nav-link" href="{{ url_for('admin.api_logs') }}">
                    <i class="fas fa-fw fa-list"></i>
                    <span>API Logs</span></a>
            </li>

            <!-- Divider -->
            <hr class="sidebar-divider">

            <!-- Heading -->
            <div class="sidebar-heading">
                Analytics & Reports
            </div>

            <!-- Nav Item - Analytics Dashboard -->
            <li class="nav-item">
                <a class="nav-link" href="{{ url_for('admin.analytics_dashboard') }}">
                    <i class="fas fa-fw fa-chart-line"></i>
                    <span>Analytics Dashboard</span></a>
            </li>

            <!-- Nav Item - Report Builder -->
            <li class="nav-item">
                <a class="nav-link" href="{{ url_for('admin.report_builder') }}">
                    <i class="fas fa-fw fa-tools"></i>
                    <span>Report Builder</span></a>
            </li>

            <!-- Nav Item - Report Templates -->
            <li class="nav-item">
                <a class="nav-link" href="{{ url_for('admin.report_templates') }}">
                    <i class="fas fa-fw fa-file-alt"></i>
                    <span>Report Templates</span></a>
            </li>

            <!-- Nav Item - Scheduled Reports -->
            <li class="nav-item">
                <a class="nav-link" href="{{ url_for('admin.scheduled_reports') }}">
                    <i class="fas fa-fw fa-clock"></i>
                    <span>Scheduled Reports</span></a>
            </li>

            <!-- Divider -->
            <hr class="sidebar-divider">

            <!-- Heading -->
            <div class="sidebar-heading">
                Monitoring
            </div>

            <!-- Nav Item - Alerts -->
            <li class="nav-item">
                <a class="nav-link" href="{{ url_for('admin.alerts') }}">
                    <i class="fas fa-fw fa-bell"></i>
                    <span>Alerts</span></a>
            </li>

            <!-- Nav Item - Alert Rules -->
            <li class="nav-item">
                <a class="nav-link" href="{{ url_for('admin.alert_rules') }}">
                    <i class="fas fa-fw fa-cog"></i>
                    <span>Alert Rules</span></a>
            </li>

            <!-- Nav Item - Monitoring Dashboard -->
            <li class="nav-item">
                <a class="nav-link" href="{{ url_for('admin.monitoring_dashboard') }}">
                    <i class="fas fa-fw fa-tachometer-alt"></i>
                    <span>Monitoring Dashboard</span></a>
            </li>

            <!-- Divider -->
            <hr class="sidebar-divider">

            <!-- Heading -->
            <div class="sidebar-heading">
                Security
            </div>

            <!-- Nav Item - Security Dashboard -->
            <li class="nav-item">
                <a class="nav-link" href="{{ url_for('admin.security_dashboard') }}">
                    <i class="fas fa-fw fa-shield-alt"></i>
                    <span>Security Dashboard</span></a>
            </li>

            <!-- Divider -->
            <hr class="sidebar-divider">

            <!-- Heading -->
            <div class="sidebar-heading">
                Bulk Operations
            </div>

            <!-- Nav Item - Bulk Operations -->
            <li class="nav-item">
                <a class="nav-link" href="{{ url_for('admin.bulk_operations') }}">
                    <i class="fas fa-fw fa-tasks"></i>
                    <span>Bulk Operations</span></a>
            </li>

            <!-- Divider -->
            <hr class="sidebar-divider">

            <!-- Heading -->
            <div class="sidebar-heading">
                Reports & Export
            </div>

            <!-- Nav Item - Bulk Export -->
            <li class="nav-item">
                <a class="nav-link" href="{{ url_for('admin.bulk_export') }}">
                    <i class="fas fa-fw fa-download"></i>
                    <span>Bulk Export</span></a>
            </li>

            <!-- Nav Item - Performance Summary -->
            <li class="nav-item">
                <a class="nav-link" href="{{ url_for('admin.performance_summary_report') }}">
                    <i class="fas fa-fw fa-chart-bar"></i>
                    <span>Performance Report</span></a>
            </li>

            <!-- Divider -->
            <hr class="sidebar-divider">

            <!-- Heading -->
            <div class="sidebar-heading">
                System
            </div>

            <!-- Nav Item - Users -->
            {% if session.get('role') == 'super_admin' %}
            <li class="nav-item">
                <a class="nav-link" href="{{ url_for('admin.users') }}">
                    <i class="fas fa-fw fa-user-shield"></i>
                    <span>Users</span></a>
            </li>
            {% endif %}

            <!-- Nav Item - Profile -->
            <li class="nav-item">
                <a class="nav-link" href="{{ url_for('auth.profile') }}">
                    <i class="fas fa-fw fa-user"></i>
                    <span>Profile</span></a>
            </li>

            <!-- Divider -->
            <hr class="sidebar-divider d-none d-md-block">

            <!-- Sidebar Toggler (Sidebar) -->
            <div class="text-center d-none d-md-inline">
                <button class="rounded-circle border-0" id="sidebarToggle"></button>
            </div>

        </ul>'''

# Templates to fix
TEMPLATES_TO_FIX = [
    'templates/admin/report_templates.html',
    'templates/admin/new_report_template.html', 
    'templates/admin/scheduled_reports.html',
    'templates/admin/new_scheduled_report.html',
    'templates/admin/report_executions.html'
]

def fix_template_sidebar(template_path):
    """Fix the sidebar in a template file"""
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find the sidebar section and replace it
        start_marker = '        <!-- Sidebar -->'
        end_marker = '        </ul>'
        
        start_pos = content.find(start_marker)
        if start_pos == -1:
            print(f"Could not find sidebar start marker in {template_path}")
            return False
            
        # Find the end of the sidebar
        end_pos = content.find(end_marker, start_pos)
        if end_pos == -1:
            print(f"Could not find sidebar end marker in {template_path}")
            return False
            
        # Replace the sidebar section
        new_content = content[:start_pos] + COMPLETE_SIDEBAR + content[end_pos + len(end_marker):]
        
        with open(template_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
            
        print(f"✅ Fixed sidebar in {template_path}")
        return True
        
    except Exception as e:
        print(f"❌ Error fixing {template_path}: {e}")
        return False

def main():
    print("Fixing sidebar navigation in analytics templates...")
    
    success_count = 0
    for template in TEMPLATES_TO_FIX:
        if os.path.exists(template):
            if fix_template_sidebar(template):
                success_count += 1
        else:
            print(f"⚠️  Template not found: {template}")
    
    print(f"\n🎉 Fixed {success_count}/{len(TEMPLATES_TO_FIX)} templates!")
    print("All analytics templates now have complete sidebar navigation.")

if __name__ == "__main__":
    main()
