#!/usr/bin/env python3
"""
Script to fix all analytics templates with proper CSS, JavaScript, and structure
"""

import os
import re

# Templates to fix
TEMPLATES_TO_FIX = [
    'templates/admin/report_templates.html',
    'templates/admin/new_report_template.html', 
    'templates/admin/scheduled_reports.html',
    'templates/admin/new_scheduled_report.html',
    'templates/admin/report_executions.html',
    'templates/admin/report_builder.html',
    'templates/admin/analytics_dashboard.html'
]

def fix_template_css_and_js(template_path):
    """Fix CSS and JavaScript in a template file"""
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Add sb-admin-2 CSS if not present
        if 'sb-admin-2.min.css' not in content:
            content = content.replace(
                '<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">',
                '''<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="{{ url_for('static', filename='css/sb-admin-2.min.css') }}" rel="stylesheet">'''
            )
        
        # Add comprehensive sidebar CSS
        sidebar_css = '''
        /* Ensure sidebar is visible and properly styled */
        .sidebar {
            position: fixed;
            top: 0;
            bottom: 0;
            left: 0;
            z-index: 100;
            padding: 48px 0 0;
            box-shadow: inset -1px 0 0 rgba(0, 0, 0, .1);
            background: linear-gradient(180deg, #4e73df 10%, #224abe 100%);
        }

        .sidebar-sticky {
            position: relative;
            top: 0;
            height: calc(100vh - 48px);
            padding-top: .5rem;
            overflow-x: hidden;
            overflow-y: auto;
        }

        .sidebar .nav-link {
            font-weight: 500;
            color: rgba(255, 255, 255, 0.8) !important;
        }

        .sidebar .nav-link:hover {
            color: #fff !important;
        }

        .sidebar .nav-link.active {
            color: #fff !important;
        }

        .sidebar-heading {
            font-size: .75rem;
            text-transform: uppercase;
            color: rgba(255, 255, 255, 0.4);
        }

        .sidebar-brand {
            color: #fff !important;
        }

        .sidebar-divider {
            border-color: rgba(255, 255, 255, 0.15);
        }

        @media (max-width: 767.98px) {
            .sidebar {
                top: 5rem;
            }
        }

        /* Content wrapper adjustments */
        #content-wrapper {
            margin-left: 0;
            width: 100%;
        }

        @media (min-width: 768px) {
            #content-wrapper {
                margin-left: 14rem;
            }
        }

        /* Sidebar toggled state */
        body.sidebar-toggled .sidebar {
            margin-left: -14rem;
        }

        body.sidebar-toggled #content-wrapper {
            margin-left: 0;
        }

        @media (max-width: 767.98px) {
            body.sidebar-toggled .sidebar {
                margin-left: 0;
            }
        }'''
        
        # Insert CSS before closing </style> tag
        if '</style>' in content:
            content = content.replace('</style>', sidebar_css + '\n    </style>')
        
        # Add JavaScript if not present
        if 'sb-admin-2.min.js' not in content:
            js_script = '''
    <!-- Custom scripts for this template-->
    <script src="{{ url_for('static', filename='js/sb-admin-2.min.js') }}"></script>

    <script>
        // Sidebar toggle functionality
        $("#sidebarToggle, #sidebarToggleTop").on('click', function(e) {
            $("body").toggleClass("sidebar-toggled");
            $(".sidebar").toggleClass("toggled");
            if ($(".sidebar").hasClass("toggled")) {
                $('.sidebar .collapse').collapse('hide');
            };
        });

        // Close any open menu accordions when window is resized below 768px
        $(window).resize(function() {
            if ($(window).width() < 768) {
                $('.sidebar .collapse').collapse('hide');
            };
        });

        // Prevent the content wrapper from scrolling when the fixed side navigation is hovered over
        $('body.fixed-nav .sidebar').on('mousewheel DOMMouseScroll wheel', function(e) {
            if ($(window).width() > 768) {
                var e0 = e.originalEvent,
                    delta = e0.wheelDelta || -e0.detail;
                this.scrollTop += (delta < 0 ? 1 : -1) * 30;
                e.preventDefault();
            }
        });

        // Scroll to top button appear
        $(document).on('scroll', function() {
            var scrollDistance = $(this).scrollTop();
            if (scrollDistance > 100) {
                $('.scroll-to-top').fadeIn();
            } else {
                $('.scroll-to-top').fadeOut();
            }
        });

        // Smooth scrolling using jQuery easing
        $(document).on('click', 'a.scroll-to-top', function(e) {
            var $anchor = $(this);
            $('html, body').stop().animate({
                scrollTop: ($($anchor.attr('href')).offset().top)
            }, 1000, 'easeInOutExpo');
            e.preventDefault();
        });
    </script>'''
            
            # Insert before closing </body> tag
            content = content.replace('</body>', js_script + '\n</body>')
        
        # Ensure proper body classes
        if 'sidebar-toggled' not in content and 'id="page-top"' in content:
            content = content.replace('id="page-top"', 'id="page-top" class="sidebar-toggled"')
        
        with open(template_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
        print(f"✅ Fixed CSS and JavaScript in {template_path}")
        return True
        
    except Exception as e:
        print(f"❌ Error fixing {template_path}: {e}")
        return False

def main():
    print("Fixing CSS and JavaScript in all analytics templates...")
    
    success_count = 0
    for template in TEMPLATES_TO_FIX:
        if os.path.exists(template):
            if fix_template_css_and_js(template):
                success_count += 1
        else:
            print(f"⚠️  Template not found: {template}")
    
    print(f"\n🎉 Fixed {success_count}/{len(TEMPLATES_TO_FIX)} templates!")
    print("All analytics templates now have proper CSS and JavaScript for sidebar functionality.")

if __name__ == "__main__":
    main()
