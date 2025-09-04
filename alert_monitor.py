"""
Alert Monitoring System for MosPay
Monitors client performance and generates alerts based on configurable rules
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from models import db, Client, Transaction, Alert, AlertRule, User
from sqlalchemy import func, and_, or_

logger = logging.getLogger(__name__)


class AlertMonitor:
    """Main alert monitoring service"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def check_all_rules(self) -> List[Alert]:
        """Check all active alert rules and generate alerts"""
        alerts_created = []
        
        try:
            # Get all active alert rules
            rules = AlertRule.query.filter_by(is_active=True).all()
            
            for rule in rules:
                try:
                    alert = self.check_rule(rule)
                    if alert:
                        alerts_created.append(alert)
                except Exception as e:
                    self.logger.error(f"Error checking rule {rule.id}: {str(e)}")
                    continue
            
            return alerts_created
            
        except Exception as e:
            self.logger.error(f"Error in check_all_rules: {str(e)}")
            return []
    
    def check_rule(self, rule: AlertRule) -> Optional[Alert]:
        """Check a specific alert rule and create alert if threshold is exceeded"""
        try:
            # Get clients to check (specific client or all clients)
            if rule.client_id:
                clients = [Client.query.get(rule.client_id)]
            else:
                clients = Client.query.filter_by(is_active=True).all()
            
            for client in clients:
                if not client:
                    continue
                
                # Calculate metric value
                metric_value = self.calculate_metric(client, rule.metric, rule.time_window)
                
                if metric_value is None:
                    continue
                
                # Check if threshold is exceeded
                if self.evaluate_threshold(metric_value, rule.threshold_value, rule.threshold_operator):
                    # Check if alert already exists for this rule and client
                    existing_alert = Alert.query.filter(
                        and_(
                            Alert.alert_type == rule.alert_type,
                            Alert.client_id == client.id,
                            Alert.status == 'active',
                            Alert.created_at >= datetime.utcnow() - timedelta(hours=rule.time_window)
                        )
                    ).first()
                    
                    if not existing_alert:
                        # Create new alert
                        alert = self.create_alert(rule, client, metric_value)
                        if alert:
                            return alert
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error checking rule {rule.id}: {str(e)}")
            return None
    
    def calculate_metric(self, client: Client, metric: str, time_window_hours: int) -> Optional[float]:
        """Calculate the metric value for a client within the time window"""
        try:
            time_window = datetime.utcnow() - timedelta(hours=time_window_hours)
            
            if metric == 'success_rate':
                return self.calculate_success_rate(client, time_window)
            elif metric == 'transaction_count':
                return self.calculate_transaction_count(client, time_window)
            elif metric == 'revenue':
                return self.calculate_revenue(client, time_window)
            elif metric == 'inactivity':
                return self.calculate_inactivity_hours(client)
            else:
                self.logger.warning(f"Unknown metric: {metric}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error calculating metric {metric} for client {client.id}: {str(e)}")
            return None
    
    def calculate_success_rate(self, client: Client, since: datetime) -> Optional[float]:
        """Calculate success rate for a client since given time"""
        try:
            total_transactions = Transaction.query.filter(
                and_(
                    Transaction.client_id == client.id,
                    Transaction.created_at >= since
                )
            ).count()
            
            if total_transactions == 0:
                return None
            
            successful_transactions = Transaction.query.filter(
                and_(
                    Transaction.client_id == client.id,
                    Transaction.created_at >= since,
                    Transaction.status == 'completed'
                )
            ).count()
            
            return (successful_transactions / total_transactions) * 100
            
        except Exception as e:
            self.logger.error(f"Error calculating success rate for client {client.id}: {str(e)}")
            return None
    
    def calculate_transaction_count(self, client: Client, since: datetime) -> float:
        """Calculate transaction count for a client since given time"""
        try:
            return Transaction.query.filter(
                and_(
                    Transaction.client_id == client.id,
                    Transaction.created_at >= since
                )
            ).count()
            
        except Exception as e:
            self.logger.error(f"Error calculating transaction count for client {client.id}: {str(e)}")
            return 0.0
    
    def calculate_revenue(self, client: Client, since: datetime) -> float:
        """Calculate revenue for a client since given time"""
        try:
            result = db.session.query(func.sum(Transaction.amount)).filter(
                and_(
                    Transaction.client_id == client.id,
                    Transaction.created_at >= since,
                    Transaction.status == 'completed'
                )
            ).scalar()
            
            return float(result) if result else 0.0
            
        except Exception as e:
            self.logger.error(f"Error calculating revenue for client {client.id}: {str(e)}")
            return 0.0
    
    def calculate_inactivity_hours(self, client: Client) -> float:
        """Calculate hours since last transaction for a client"""
        try:
            last_transaction = Transaction.query.filter_by(
                client_id=client.id
            ).order_by(Transaction.created_at.desc()).first()
            
            if not last_transaction:
                # If no transactions, use client creation date
                return (datetime.utcnow() - client.created_at).total_seconds() / 3600
            
            return (datetime.utcnow() - last_transaction.created_at).total_seconds() / 3600
            
        except Exception as e:
            self.logger.error(f"Error calculating inactivity for client {client.id}: {str(e)}")
            return 0.0
    
    def evaluate_threshold(self, value: float, threshold: float, operator: str) -> bool:
        """Evaluate if value meets threshold condition"""
        try:
            if operator == '>':
                return value > threshold
            elif operator == '<':
                return value < threshold
            elif operator == '>=':
                return value >= threshold
            elif operator == '<=':
                return value <= threshold
            elif operator == '==':
                return value == threshold
            elif operator == '!=':
                return value != threshold
            else:
                self.logger.warning(f"Unknown operator: {operator}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error evaluating threshold: {str(e)}")
            return False
    
    def create_alert(self, rule: AlertRule, client: Client, metric_value: float) -> Optional[Alert]:
        """Create a new alert based on rule and client data"""
        try:
            # Generate alert title and message
            title, message = self.generate_alert_content(rule, client, metric_value)
            
            # Determine severity based on rule type and threshold
            severity = self.determine_severity(rule, metric_value)
            
            # Create alert
            alert = Alert(
                alert_type=rule.alert_type,
                title=title,
                message=message,
                severity=severity,
                status='active',
                client_id=client.id,
                alert_data={
                    'rule_id': rule.id,
                    'rule_name': rule.name,
                    'metric': rule.metric,
                    'metric_value': metric_value,
                    'threshold_value': rule.threshold_value,
                    'threshold_operator': rule.threshold_operator,
                    'time_window': rule.time_window
                }
            )
            
            db.session.add(alert)
            db.session.commit()
            
            self.logger.info(f"Created alert: {title} for client {client.company_name}")
            return alert
            
        except Exception as e:
            self.logger.error(f"Error creating alert: {str(e)}")
            db.session.rollback()
            return None
    
    def generate_alert_content(self, rule: AlertRule, client: Client, metric_value: float) -> tuple:
        """Generate alert title and message"""
        try:
            metric_name = self.get_metric_display_name(rule.metric)
            operator_name = self.get_operator_display_name(rule.threshold_operator)
            
            title = f"{client.company_name} - {rule.name}"
            
            if rule.metric == 'success_rate':
                message = f"Success rate is {metric_value:.1f}% (threshold: {operator_name} {rule.threshold_value}%)"
            elif rule.metric == 'transaction_count':
                message = f"Transaction count is {int(metric_value)} (threshold: {operator_name} {rule.threshold_value})"
            elif rule.metric == 'revenue':
                message = f"Revenue is ${metric_value:.2f} (threshold: {operator_name} ${rule.threshold_value})"
            elif rule.metric == 'inactivity':
                message = f"Client inactive for {metric_value:.1f} hours (threshold: {operator_name} {rule.threshold_value} hours)"
            else:
                message = f"{metric_name} is {metric_value} (threshold: {operator_name} {rule.threshold_value})"
            
            return title, message
            
        except Exception as e:
            self.logger.error(f"Error generating alert content: {str(e)}")
            return "Alert", "Performance threshold exceeded"
    
    def get_metric_display_name(self, metric: str) -> str:
        """Get display name for metric"""
        names = {
            'success_rate': 'Success Rate',
            'transaction_count': 'Transaction Count',
            'revenue': 'Revenue',
            'inactivity': 'Inactivity Period'
        }
        return names.get(metric, metric.title())
    
    def get_operator_display_name(self, operator: str) -> str:
        """Get display name for operator"""
        names = {
            '>': 'greater than',
            '<': 'less than',
            '>=': 'greater than or equal to',
            '<=': 'less than or equal to',
            '==': 'equal to',
            '!=': 'not equal to'
        }
        return names.get(operator, operator)
    
    def determine_severity(self, rule: AlertRule, metric_value: float) -> str:
        """Determine alert severity based on rule and metric value"""
        try:
            # Base severity on how far the metric is from threshold
            if rule.metric == 'success_rate':
                if metric_value < 50:
                    return 'critical'
                elif metric_value < 70:
                    return 'error'
                elif metric_value < 85:
                    return 'warning'
                else:
                    return 'info'
            elif rule.metric == 'inactivity':
                if metric_value > 168:  # 1 week
                    return 'critical'
                elif metric_value > 72:  # 3 days
                    return 'error'
                elif metric_value > 24:  # 1 day
                    return 'warning'
                else:
                    return 'info'
            else:
                return 'warning'
                
        except Exception as e:
            self.logger.error(f"Error determining severity: {str(e)}")
            return 'warning'
    
    def acknowledge_alert(self, alert_id: int, user_id: int) -> bool:
        """Acknowledge an alert"""
        try:
            alert = Alert.query.get(alert_id)
            if not alert:
                return False
            
            alert.status = 'acknowledged'
            alert.acknowledged_at = datetime.utcnow()
            alert.acknowledged_by = user_id
            
            db.session.commit()
            return True
            
        except Exception as e:
            self.logger.error(f"Error acknowledging alert {alert_id}: {str(e)}")
            db.session.rollback()
            return False
    
    def resolve_alert(self, alert_id: int, user_id: int) -> bool:
        """Resolve an alert"""
        try:
            alert = Alert.query.get(alert_id)
            if not alert:
                return False
            
            alert.status = 'resolved'
            alert.resolved_at = datetime.utcnow()
            alert.resolved_by = user_id
            
            db.session.commit()
            return True
            
        except Exception as e:
            self.logger.error(f"Error resolving alert {alert_id}: {str(e)}")
            db.session.rollback()
            return False


# Global alert monitor instance
alert_monitor = AlertMonitor()
