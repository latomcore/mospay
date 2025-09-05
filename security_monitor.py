"""
Security Monitoring System for MosPay
Advanced security monitoring, fraud detection, and threat prevention
"""

from datetime import datetime, timedelta
from flask import request, current_app
from models import db, SecurityEvent, IPBlacklist, RateLimit, FraudDetection, Transaction, Client
from sqlalchemy import and_, or_
import json
import hashlib


class SecurityMonitor:
    """Main security monitoring class"""
    
    def __init__(self):
        self.fraud_rules = self._load_fraud_rules()
    
    def _load_fraud_rules(self):
        """Load fraud detection rules"""
        return {
            'high_amount': {'threshold': 10000, 'weight': 0.3},
            'rapid_transactions': {'threshold': 5, 'time_window': 300, 'weight': 0.4},  # 5 transactions in 5 minutes
            'unusual_hours': {'start_hour': 22, 'end_hour': 6, 'weight': 0.2},
            'new_client': {'days_threshold': 7, 'weight': 0.3},
            'failed_attempts': {'threshold': 3, 'time_window': 600, 'weight': 0.5}  # 3 failed attempts in 10 minutes
        }
    
    def log_security_event(self, event_type, title, description, severity='medium', 
                          ip_address=None, user_id=None, client_id=None, transaction_id=None, 
                          event_data=None):
        """Log a security event"""
        try:
            # Get IP address from request if not provided
            if not ip_address:
                ip_address = self._get_client_ip()
            
            # Get user agent
            user_agent = request.headers.get('User-Agent') if request else None
            
            # Create security event
            event = SecurityEvent(
                event_type=event_type,
                severity=severity,
                title=title,
                description=description,
                ip_address=ip_address,
                user_agent=user_agent,
                user_id=user_id,
                client_id=client_id,
                transaction_id=transaction_id,
                event_data=event_data or {}
            )
            
            db.session.add(event)
            db.session.commit()
            
            print(f"[SECURITY] Event logged: {event_type} - {title}")
            return event
            
        except Exception as e:
            print(f"[SECURITY] Error logging event: {str(e)}")
            db.session.rollback()
            return None
    
    def check_rate_limit(self, identifier, identifier_type='ip', endpoint=None, 
                        limit=100, window_duration=3600):
        """Check and enforce rate limiting"""
        try:
            # Clean up old rate limit records
            self._cleanup_rate_limits()
            
            # Check if identifier is blocked
            if self._is_identifier_blocked(identifier, identifier_type):
                return False, "Rate limit exceeded - temporarily blocked"
            
            # Get or create rate limit record
            rate_limit = RateLimit.query.filter_by(
                identifier=identifier,
                identifier_type=identifier_type,
                endpoint=endpoint
            ).first()
            
            now = datetime.utcnow()
            
            if not rate_limit:
                # Create new rate limit record
                rate_limit = RateLimit(
                    identifier=identifier,
                    identifier_type=identifier_type,
                    endpoint=endpoint,
                    request_count=1,
                    window_start=now,
                    window_duration=window_duration,
                    limit_threshold=limit
                )
                db.session.add(rate_limit)
            else:
                # Check if window has expired
                if now - rate_limit.window_start > timedelta(seconds=window_duration):
                    # Reset window
                    rate_limit.request_count = 1
                    rate_limit.window_start = now
                    rate_limit.is_blocked = False
                    rate_limit.blocked_until = None
                else:
                    # Increment count
                    rate_limit.request_count += 1
                
                rate_limit.updated_at = now
            
            db.session.commit()
            
            # Check if limit exceeded
            if rate_limit.request_count > limit:
                # Block the identifier temporarily
                rate_limit.is_blocked = True
                rate_limit.blocked_until = now + timedelta(hours=1)  # Block for 1 hour
                db.session.commit()
                
                # Log security event
                self.log_security_event(
                    'rate_limit_exceeded',
                    f'Rate limit exceeded for {identifier_type}: {identifier}',
                    f'Rate limit of {limit} requests per {window_duration} seconds exceeded. Current count: {rate_limit.request_count}',
                    severity='high',
                    ip_address=identifier if identifier_type == 'ip' else None,
                    event_data={
                        'identifier': identifier,
                        'identifier_type': identifier_type,
                        'endpoint': endpoint,
                        'request_count': rate_limit.request_count,
                        'limit': limit,
                        'window_duration': window_duration
                    }
                )
                
                return False, f"Rate limit exceeded. Blocked until {rate_limit.blocked_until}"
            
            return True, "Rate limit OK"
            
        except Exception as e:
            print(f"[SECURITY] Rate limit check error: {str(e)}")
            db.session.rollback()
            return True, "Rate limit check failed - allowing request"
    
    def check_ip_blacklist(self, ip_address):
        """Check if IP address is blacklisted"""
        try:
            blacklist_entry = IPBlacklist.query.filter_by(
                ip_address=ip_address,
                is_active=True
            ).first()
            
            if blacklist_entry:
                # Check if block has expired
                if blacklist_entry.expires_at and datetime.utcnow() > blacklist_entry.expires_at:
                    blacklist_entry.is_active = False
                    db.session.commit()
                    return False, "Block expired"
                
                return True, f"IP blocked: {blacklist_entry.reason}"
            
            return False, "IP not blacklisted"
            
        except Exception as e:
            print(f"[SECURITY] IP blacklist check error: {str(e)}")
            return False, "Blacklist check failed"
    
    def block_ip(self, ip_address, reason, blocked_by=None, expires_at=None):
        """Block an IP address"""
        try:
            # Check if already blocked
            existing = IPBlacklist.query.filter_by(ip_address=ip_address).first()
            
            if existing:
                if existing.is_active:
                    return False, "IP already blocked"
                else:
                    # Reactivate existing block
                    existing.is_active = True
                    existing.reason = reason
                    existing.blocked_by = blocked_by
                    existing.blocked_at = datetime.utcnow()
                    existing.expires_at = expires_at
                    existing.event_count += 1
            else:
                # Create new block
                block = IPBlacklist(
                    ip_address=ip_address,
                    reason=reason,
                    blocked_by=blocked_by,
                    expires_at=expires_at
                )
                db.session.add(block)
            
            db.session.commit()
            
            # Log security event
            self.log_security_event(
                'ip_blocked',
                f'IP address blocked: {ip_address}',
                f'IP address {ip_address} has been blocked. Reason: {reason}',
                severity='high',
                ip_address=ip_address,
                user_id=blocked_by,
                event_data={
                    'ip_address': ip_address,
                    'reason': reason,
                    'expires_at': expires_at.isoformat() if expires_at else None
                }
            )
            
            return True, "IP blocked successfully"
            
        except Exception as e:
            print(f"[SECURITY] IP block error: {str(e)}")
            db.session.rollback()
            return False, f"Failed to block IP: {str(e)}"
    
    def analyze_transaction_fraud(self, transaction):
        """Analyze transaction for fraud indicators"""
        try:
            risk_score = 0.0
            risk_factors = []
            triggered_rules = []
            
            # Rule 1: High amount transactions
            if transaction.amount and transaction.amount > self.fraud_rules['high_amount']['threshold']:
                risk_score += self.fraud_rules['high_amount']['weight']
                risk_factors.append(f"High amount: ${transaction.amount}")
                triggered_rules.append('high_amount')
            
            # Rule 2: Rapid transactions from same client
            recent_transactions = Transaction.query.filter(
                Transaction.client_id == transaction.client_id,
                Transaction.created_at >= datetime.utcnow() - timedelta(seconds=self.fraud_rules['rapid_transactions']['time_window'])
            ).count()
            
            if recent_transactions > self.fraud_rules['rapid_transactions']['threshold']:
                risk_score += self.fraud_rules['rapid_transactions']['weight']
                risk_factors.append(f"Rapid transactions: {recent_transactions} in {self.fraud_rules['rapid_transactions']['time_window']}s")
                triggered_rules.append('rapid_transactions')
            
            # Rule 3: Unusual hours (late night/early morning)
            current_hour = datetime.utcnow().hour
            if (current_hour >= self.fraud_rules['unusual_hours']['start_hour'] or 
                current_hour <= self.fraud_rules['unusual_hours']['end_hour']):
                risk_score += self.fraud_rules['unusual_hours']['weight']
                risk_factors.append(f"Unusual hours: {current_hour}:00")
                triggered_rules.append('unusual_hours')
            
            # Rule 4: New client
            client = Client.query.get(transaction.client_id)
            if client and (datetime.utcnow() - client.created_at).days < self.fraud_rules['new_client']['days_threshold']:
                risk_score += self.fraud_rules['new_client']['weight']
                risk_factors.append(f"New client: {client.company_name}")
                triggered_rules.append('new_client')
            
            # Create fraud detection record
            fraud_analysis = FraudDetection(
                transaction_id=transaction.id,
                client_id=transaction.client_id,
                risk_score=min(risk_score, 1.0),  # Cap at 1.0
                risk_factors=risk_factors,
                fraud_rules_triggered=triggered_rules,
                status='pending' if risk_score > 0.5 else 'approved'
            )
            
            db.session.add(fraud_analysis)
            db.session.commit()
            
            # Log security event if high risk
            if risk_score > 0.5:
                self.log_security_event(
                    'suspicious_transaction',
                    f'High-risk transaction detected: {transaction.unique_id}',
                    f'Transaction {transaction.unique_id} flagged for fraud. Risk score: {risk_score:.2f}',
                    severity='high' if risk_score > 0.8 else 'medium',
                    client_id=transaction.client_id,
                    transaction_id=transaction.id,
                    event_data={
                        'transaction_id': transaction.id,
                        'risk_score': risk_score,
                        'risk_factors': risk_factors,
                        'triggered_rules': triggered_rules
                    }
                )
            
            return fraud_analysis
            
        except Exception as e:
            print(f"[SECURITY] Fraud analysis error: {str(e)}")
            db.session.rollback()
            return None
    
    def get_security_summary(self, hours=24):
        """Get security summary for the last N hours"""
        try:
            since = datetime.utcnow() - timedelta(hours=hours)
            
            # Count events by type and severity
            events = SecurityEvent.query.filter(SecurityEvent.created_at >= since).all()
            
            summary = {
                'total_events': len(events),
                'by_type': {},
                'by_severity': {},
                'recent_events': [],
                'blocked_ips': IPBlacklist.query.filter_by(is_active=True).count(),
                'rate_limited': RateLimit.query.filter_by(is_blocked=True).count(),
                'fraud_alerts': FraudDetection.query.filter(
                    FraudDetection.created_at >= since,
                    FraudDetection.status == 'pending'
                ).count()
            }
            
            # Group by type and severity
            for event in events:
                # By type
                if event.event_type not in summary['by_type']:
                    summary['by_type'][event.event_type] = 0
                summary['by_type'][event.event_type] += 1
                
                # By severity
                if event.severity not in summary['by_severity']:
                    summary['by_severity'][event.severity] = 0
                summary['by_severity'][event.severity] += 1
            
            # Get recent events (last 10)
            summary['recent_events'] = [
                {
                    'id': event.id,
                    'type': event.event_type,
                    'severity': event.severity,
                    'title': event.title,
                    'ip_address': event.ip_address,
                    'created_at': event.created_at.isoformat()
                }
                for event in events[-10:]
            ]
            
            return summary
            
        except Exception as e:
            print(f"[SECURITY] Summary error: {str(e)}")
            return {}
    
    def _get_client_ip(self):
        """Get client IP address from request"""
        if not request:
            return None
        
        # Check for forwarded IPs (behind proxy/load balancer)
        forwarded_for = request.headers.get('X-Forwarded-For')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        
        real_ip = request.headers.get('X-Real-IP')
        if real_ip:
            return real_ip
        
        return request.remote_addr
    
    def _is_identifier_blocked(self, identifier, identifier_type):
        """Check if identifier is currently blocked"""
        try:
            rate_limit = RateLimit.query.filter_by(
                identifier=identifier,
                identifier_type=identifier_type,
                is_blocked=True
            ).first()
            
            if rate_limit and rate_limit.blocked_until:
                if datetime.utcnow() < rate_limit.blocked_until:
                    return True
                else:
                    # Unblock expired entries
                    rate_limit.is_blocked = False
                    rate_limit.blocked_until = None
                    db.session.commit()
            
            return False
            
        except Exception as e:
            print(f"[SECURITY] Block check error: {str(e)}")
            return False
    
    def _cleanup_rate_limits(self):
        """Clean up old rate limit records"""
        try:
            # Remove records older than 24 hours
            cutoff = datetime.utcnow() - timedelta(hours=24)
            RateLimit.query.filter(RateLimit.created_at < cutoff).delete()
            db.session.commit()
        except Exception as e:
            print(f"[SECURITY] Cleanup error: {str(e)}")
            db.session.rollback()


# Global security monitor instance
security_monitor = SecurityMonitor()
