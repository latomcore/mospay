"""
PDF Export Utilities for MosPay
Professional PDF report generation using ReportLab
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.platypus import Image
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from datetime import datetime
import io
from flask import make_response


class PDFGenerator:
    """Professional PDF report generator for MosPay"""
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.setup_custom_styles()
    
    def setup_custom_styles(self):
        """Setup custom styles for professional appearance"""
        # Title style
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Title'],
            fontSize=24,
            spaceAfter=30,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#2c3e50')
        ))
        
        # Subtitle style
        self.styles.add(ParagraphStyle(
            name='CustomSubtitle',
            parent=self.styles['Heading2'],
            fontSize=16,
            spaceAfter=20,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#34495e')
        ))
        
        # Header style
        self.styles.add(ParagraphStyle(
            name='CustomHeader',
            parent=self.styles['Heading3'],
            fontSize=14,
            spaceAfter=15,
            textColor=colors.HexColor('#2c3e50')
        ))
        
        # Normal text style
        self.styles.add(ParagraphStyle(
            name='CustomNormal',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=6
        ))
        
        # Footer style
        self.styles.add(ParagraphStyle(
            name='CustomFooter',
            parent=self.styles['Normal'],
            fontSize=8,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#7f8c8d')
        ))

    def create_transactions_pdf(self, transactions, client_ids, start_date, end_date):
        """Create a professional transactions PDF report"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, 
                              topMargin=72, bottomMargin=18)
        
        # Build the content
        story = []
        
        # Logo and Title
        try:
            logo = Image('static/images/mospay_image_black_background.png', width=2*inch, height=0.8*inch)
            story.append(logo)
            story.append(Spacer(1, 12))
        except:
            # Fallback if logo not found
            pass
        
        story.append(Paragraph("MosPay Transaction Report", self.styles['CustomTitle']))
        story.append(Spacer(1, 12))
        
        # Report info
        report_date = datetime.now().strftime("%B %d, %Y at %I:%M %p")
        story.append(Paragraph(f"Generated on {report_date}", self.styles['CustomSubtitle']))
        story.append(Spacer(1, 20))
        
        # Filter information
        filter_info = []
        if start_date and end_date:
            filter_info.append(f"Date Range: {start_date} to {end_date}")
        if client_ids:
            filter_info.append(f"Client IDs: {', '.join(map(str, client_ids))}")
        
        if filter_info:
            story.append(Paragraph("Report Filters:", self.styles['CustomHeader']))
            for info in filter_info:
                story.append(Paragraph(f"• {info}", self.styles['CustomNormal']))
            story.append(Spacer(1, 20))
        
        # Summary statistics
        if transactions:
            total_amount = sum(t.amount or 0 for t in transactions)
            completed_count = sum(1 for t in transactions if t.status == 'completed')
            success_rate = (completed_count / len(transactions) * 100) if transactions else 0
            
            summary_data = [
                ['Total Transactions', str(len(transactions))],
                ['Completed Transactions', str(completed_count)],
                ['Success Rate', f"{success_rate:.1f}%"],
                ['Total Amount', f"${total_amount:,.2f}"]
            ]
            
            summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
            summary_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#ecf0f1')),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            
            story.append(Paragraph("Summary Statistics", self.styles['CustomHeader']))
            story.append(summary_table)
            story.append(Spacer(1, 20))
        
        # Transactions table
        if transactions:
            story.append(Paragraph("Transaction Details", self.styles['CustomHeader']))
            
            # Prepare table data
            table_data = [['ID', 'Client', 'Service', 'Status', 'Amount', 'Mobile', 'Date']]
            
            for transaction in transactions:
                table_data.append([
                    transaction.unique_id or 'N/A',
                    transaction.client.company_name if transaction.client else 'Unknown',
                    transaction.service.display_name if transaction.service else 'Unknown',
                    transaction.status or 'N/A',
                    f"${transaction.amount:,.2f}" if transaction.amount else 'N/A',
                    transaction.mobile_number or 'N/A',
                    transaction.created_at.strftime('%Y-%m-%d %H:%M') if transaction.created_at else 'N/A'
                ])
            
            # Create table
            table = Table(table_data, colWidths=[1.2*inch, 1.5*inch, 1.2*inch, 0.8*inch, 0.8*inch, 1*inch, 1*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')])
            ]))
            
            story.append(table)
        else:
            story.append(Paragraph("No transactions found matching the specified criteria.", self.styles['CustomNormal']))
        
        # Footer
        story.append(Spacer(1, 30))
        story.append(Paragraph("This report was generated by MosPay Payment Gateway System", self.styles['CustomFooter']))
        
        # Build PDF
        doc.build(story)
        buffer.seek(0)
        return buffer

    def create_clients_pdf(self, clients_data):
        """Create a professional clients PDF report"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, 
                              topMargin=72, bottomMargin=18)
        
        # Build the content
        story = []
        
        # Logo and Title
        try:
            logo = Image('static/images/mospay_image_black_background.png', width=2*inch, height=0.8*inch)
            story.append(logo)
            story.append(Spacer(1, 12))
        except:
            # Fallback if logo not found
            pass
        
        story.append(Paragraph("MosPay Client Performance Report", self.styles['CustomTitle']))
        story.append(Spacer(1, 12))
        
        # Report info
        report_date = datetime.now().strftime("%B %d, %Y at %I:%M %p")
        story.append(Paragraph(f"Generated on {report_date}", self.styles['CustomSubtitle']))
        story.append(Spacer(1, 20))
        
        # Summary statistics
        if clients_data:
            total_clients = len(clients_data)
            active_clients = sum(1 for client in clients_data if client.get('is_active', False))
            total_revenue = sum(client.get('revenue_30d', 0) for client in clients_data)
            
            summary_data = [
                ['Total Clients', str(total_clients)],
                ['Active Clients', str(active_clients)],
                ['Total Revenue (30d)', f"${total_revenue:,.2f}"],
                ['Average Revenue per Client', f"${total_revenue/total_clients:,.2f}" if total_clients > 0 else "$0.00"]
            ]
            
            summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
            summary_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#27ae60')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#d5f4e6')),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            
            story.append(Paragraph("Summary Statistics", self.styles['CustomHeader']))
            story.append(summary_table)
            story.append(Spacer(1, 20))
        
        # Clients table
        if clients_data:
            story.append(Paragraph("Client Performance Details", self.styles['CustomHeader']))
            
            # Prepare table data
            table_data = [['Company', 'Contact', 'Email', 'Status', 'Transactions', 'Success Rate', 'Revenue (30d)']]
            
            for client in clients_data:
                table_data.append([
                    client.get('company_name', 'N/A'),
                    client.get('contact_person', 'N/A'),
                    client.get('email', 'N/A'),
                    'Active' if client.get('is_active', False) else 'Inactive',
                    str(client.get('total_transactions', 0)),
                    f"{client.get('success_rate', 0):.1f}%",
                    f"${client.get('revenue_30d', 0):,.2f}"
                ])
            
            # Create table
            table = Table(table_data, colWidths=[1.5*inch, 1.2*inch, 1.8*inch, 0.8*inch, 0.8*inch, 0.8*inch, 1*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')])
            ]))
            
            story.append(table)
        else:
            story.append(Paragraph("No client data available.", self.styles['CustomNormal']))
        
        # Footer
        story.append(Spacer(1, 30))
        story.append(Paragraph("This report was generated by MosPay Payment Gateway System", self.styles['CustomFooter']))
        
        # Build PDF
        doc.build(story)
        buffer.seek(0)
        return buffer


def create_pdf_response(pdf_buffer, filename):
    """Create Flask response for PDF download"""
    response = make_response(pdf_buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return response
