from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from sqlalchemy import func, and_, extract
from src.models.financial import (
    Transaction, Category, Account, Goal, SpendingLimit, 
    RecurringTransaction, TransactionType, db
)
from typing import Dict, List, Tuple, Optional
from enum import Enum

class AlertType(Enum):
    SPENDING_LIMIT_WARNING = "spending_limit_warning"
    SPENDING_LIMIT_EXCEEDED = "spending_limit_exceeded"
    GOAL_BEHIND_SCHEDULE = "goal_behind_schedule"
    GOAL_DEADLINE_APPROACHING = "goal_deadline_approaching"
    LOW_BALANCE_PROJECTION = "low_balance_projection"
    UNUSUAL_SPENDING = "unusual_spending"
    BILL_REMINDER = "bill_reminder"
    POSITIVE_TREND = "positive_trend"

class AlertPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class Alert:
    def __init__(self, alert_type: AlertType, priority: AlertPriority, title: str, 
                 message: str, data: Dict = None, action_url: str = None):
        self.alert_type = alert_type
        self.priority = priority
        self.title = title
        self.message = message
        self.data = data or {}
        self.action_url = action_url
        self.created_at = datetime.utcnow()
        self.is_read = False

    def to_dict(self):
        return {
            'type': self.alert_type.value,
            'priority': self.priority.value,
            'title': self.title,
            'message': self.message,
            'data': self.data,
            'action_url': self.action_url,
            'created_at': self.created_at.isoformat(),
            'is_read': self.is_read
        }

class AlertSystem:
    """Sistema de alertas e notificações financeiras"""
    
    def __init__(self):
        self.current_date = date.today()
        self.alerts = []
    
    def generate_all_alerts(self) -> List[Alert]:
        """Gera todos os alertas baseados no estado atual do sistema"""
        self.alerts = []
        
        # Alertas de limites de gastos
        self._check_spending_limits()
        
        # Alertas de metas
        self._check_goals_progress()
        
        # Alertas de projeções
        self._check_balance_projections()
        
        # Alertas de gastos incomuns
        self._check_unusual_spending()
        
        # Lembretes de contas
        self._check_bill_reminders()
        
        # Alertas positivos
        self._check_positive_trends()
        
        return self.alerts
    
    def _check_spending_limits(self):
        """Verifica alertas relacionados aos limites de gastos"""
        current_month = self.current_date.month
        current_year = self.current_date.year
        month_year = f"{current_year}-{current_month:02d}"
        
        # Buscar limites do mês atual
        limits = db.session.query(SpendingLimit).filter(
            SpendingLimit.month_year == month_year
        ).all()
        
        for limit in limits:
            # Calcular gastos atuais da categoria
            start_of_month = date(current_year, current_month, 1)
            current_spent = db.session.query(
                func.sum(Transaction.amount)
            ).filter(
                and_(
                    Transaction.category_id == limit.category_id,
                    Transaction.transaction_date >= start_of_month,
                    Transaction.transaction_date <= self.current_date,
                    Transaction.transaction_type == TransactionType.EXPENSE
                )
            ).scalar() or 0.0
            
            percentage_used = (current_spent / limit.monthly_limit) * 100 if limit.monthly_limit > 0 else 0
            
            # Limite excedido
            if current_spent > limit.monthly_limit:
                excess = current_spent - limit.monthly_limit
                alert = Alert(
                    alert_type=AlertType.SPENDING_LIMIT_EXCEEDED,
                    priority=AlertPriority.HIGH,
                    title=f"Limite excedido: {limit.category.name}",
                    message=f"Você excedeu o limite de {self._format_currency(limit.monthly_limit)} "
                           f"em {limit.category.name} por {self._format_currency(excess)}.",
                    data={
                        'category_id': limit.category_id,
                        'category_name': limit.category.name,
                        'limit': limit.monthly_limit,
                        'spent': current_spent,
                        'excess': excess,
                        'percentage': percentage_used
                    },
                    action_url="/transactions?category=" + str(limit.category_id)
                )
                self.alerts.append(alert)
            
            # Aviso de aproximação do limite (80%)
            elif percentage_used >= 80:
                remaining = limit.monthly_limit - current_spent
                alert = Alert(
                    alert_type=AlertType.SPENDING_LIMIT_WARNING,
                    priority=AlertPriority.MEDIUM,
                    title=f"Atenção: {limit.category.name}",
                    message=f"Você já gastou {percentage_used:.1f}% do limite em {limit.category.name}. "
                           f"Restam {self._format_currency(remaining)}.",
                    data={
                        'category_id': limit.category_id,
                        'category_name': limit.category.name,
                        'limit': limit.monthly_limit,
                        'spent': current_spent,
                        'remaining': remaining,
                        'percentage': percentage_used
                    },
                    action_url="/transactions?category=" + str(limit.category_id)
                )
                self.alerts.append(alert)
    
    def _check_goals_progress(self):
        """Verifica alertas relacionados ao progresso das metas"""
        goals = db.session.query(Goal).filter(Goal.is_active == True).all()
        
        for goal in goals:
            days_remaining = (goal.target_date - self.current_date).days
            months_remaining = max(0, days_remaining / 30.44)
            
            # Meta com prazo se aproximando (30 dias)
            if 0 < days_remaining <= 30:
                progress_percentage = (goal.current_amount / goal.target_amount) * 100 if goal.target_amount > 0 else 0
                
                if progress_percentage < 90:  # Meta não está próxima de ser concluída
                    alert = Alert(
                        alert_type=AlertType.GOAL_DEADLINE_APPROACHING,
                        priority=AlertPriority.HIGH,
                        title=f"Meta próxima do prazo: {goal.name}",
                        message=f"Sua meta '{goal.name}' vence em {days_remaining} dias e está "
                               f"{progress_percentage:.1f}% concluída.",
                        data={
                            'goal_id': goal.id,
                            'goal_name': goal.name,
                            'target_amount': goal.target_amount,
                            'current_amount': goal.current_amount,
                            'progress_percentage': progress_percentage,
                            'days_remaining': days_remaining
                        },
                        action_url="/goals"
                    )
                    self.alerts.append(alert)
            
            # Meta atrasada em relação ao cronograma ideal
            if months_remaining > 0:
                ideal_progress = 1 - (months_remaining / self._calculate_total_months(goal))
                actual_progress = goal.current_amount / goal.target_amount if goal.target_amount > 0 else 0
                
                if actual_progress < ideal_progress - 0.1:  # 10% de tolerância
                    amount_needed = goal.target_amount - goal.current_amount
                    monthly_needed = amount_needed / months_remaining if months_remaining > 0 else amount_needed
                    
                    alert = Alert(
                        alert_type=AlertType.GOAL_BEHIND_SCHEDULE,
                        priority=AlertPriority.MEDIUM,
                        title=f"Meta atrasada: {goal.name}",
                        message=f"Sua meta '{goal.name}' está atrasada. Você precisa poupar "
                               f"{self._format_currency(monthly_needed)} por mês para alcançá-la.",
                        data={
                            'goal_id': goal.id,
                            'goal_name': goal.name,
                            'ideal_progress': ideal_progress * 100,
                            'actual_progress': actual_progress * 100,
                            'monthly_needed': monthly_needed,
                            'months_remaining': months_remaining
                        },
                        action_url="/goals"
                    )
                    self.alerts.append(alert)
    
    def _check_balance_projections(self):
        """Verifica alertas relacionados às projeções de saldo"""
        from src.services.financial_analysis import FinancialAnalyzer
        
        analyzer = FinancialAnalyzer()
        savings_capacity = analyzer.calculate_savings_capacity(3)
        
        # Verificar se algum mês terá saldo negativo
        for month_key, data in savings_capacity.items():
            if data['projected_savings'] < 0:
                alert = Alert(
                    alert_type=AlertType.LOW_BALANCE_PROJECTION,
                    priority=AlertPriority.HIGH,
                    title=f"Saldo negativo projetado",
                    message=f"Em {data['month']} de {data['year']}, suas despesas podem exceder "
                           f"as receitas em {self._format_currency(abs(data['projected_savings']))}.",
                    data={
                        'month': data['month'],
                        'year': data['year'],
                        'projected_income': data['projected_income'],
                        'projected_expenses': data['projected_expenses'],
                        'projected_deficit': abs(data['projected_savings'])
                    },
                    action_url="/projections"
                )
                self.alerts.append(alert)
                break  # Apenas um alerta para o primeiro mês problemático
    
    def _check_unusual_spending(self):
        """Verifica gastos incomuns baseados no histórico"""
        # Gastos dos últimos 7 dias
        week_ago = self.current_date - timedelta(days=7)
        
        recent_expenses = db.session.query(
            func.sum(Transaction.amount)
        ).filter(
            and_(
                Transaction.transaction_date >= week_ago,
                Transaction.transaction_date <= self.current_date,
                Transaction.transaction_type == TransactionType.EXPENSE
            )
        ).scalar() or 0.0
        
        # Média semanal dos últimos 3 meses
        three_months_ago = self.current_date - relativedelta(months=3)
        
        historical_weekly_avg = db.session.query(
            func.avg(Transaction.amount)
        ).filter(
            and_(
                Transaction.transaction_date >= three_months_ago,
                Transaction.transaction_date < week_ago,
                Transaction.transaction_type == TransactionType.EXPENSE
            )
        ).scalar() or 0.0
        
        historical_weekly_avg *= 7  # Converter para total semanal
        
        # Se os gastos da semana são 50% maiores que a média
        if recent_expenses > historical_weekly_avg * 1.5 and historical_weekly_avg > 0:
            excess = recent_expenses - historical_weekly_avg
            alert = Alert(
                alert_type=AlertType.UNUSUAL_SPENDING,
                priority=AlertPriority.MEDIUM,
                title="Gastos acima do normal",
                message=f"Seus gastos desta semana ({self._format_currency(recent_expenses)}) "
                       f"estão {self._format_currency(excess)} acima da média histórica.",
                data={
                    'recent_expenses': recent_expenses,
                    'historical_average': historical_weekly_avg,
                    'excess': excess,
                    'percentage_increase': ((recent_expenses / historical_weekly_avg) - 1) * 100
                },
                action_url="/transactions"
            )
            self.alerts.append(alert)
    
    def _check_bill_reminders(self):
        """Verifica lembretes de contas recorrentes"""
        # Buscar transações recorrentes que devem ocorrer nos próximos 7 dias
        next_week = self.current_date + timedelta(days=7)
        
        recurring_transactions = db.session.query(RecurringTransaction).filter(
            and_(
                RecurringTransaction.is_active == True,
                RecurringTransaction.transaction_type == TransactionType.EXPENSE,
                RecurringTransaction.next_occurrence <= next_week,
                RecurringTransaction.next_occurrence >= self.current_date
            )
        ).all()
        
        for transaction in recurring_transactions:
            days_until = (transaction.next_occurrence - self.current_date).days
            
            alert = Alert(
                alert_type=AlertType.BILL_REMINDER,
                priority=AlertPriority.LOW,
                title=f"Lembrete: {transaction.description}",
                message=f"A conta '{transaction.description}' de {self._format_currency(transaction.amount)} "
                       f"vence em {days_until} dia(s).",
                data={
                    'transaction_id': transaction.id,
                    'description': transaction.description,
                    'amount': transaction.amount,
                    'due_date': transaction.next_occurrence.isoformat(),
                    'days_until': days_until,
                    'category': transaction.category.name
                },
                action_url="/transactions"
            )
            self.alerts.append(alert)
    
    def _check_positive_trends(self):
        """Verifica tendências positivas para alertas motivacionais"""
        # Verificar se o usuário está economizando mais que o mês passado
        current_month = self.current_date.month
        current_year = self.current_date.year
        
        # Saldo do mês atual (até agora)
        start_of_month = date(current_year, current_month, 1)
        current_month_income = self._get_month_income(current_year, current_month, start_of_month, self.current_date)
        current_month_expenses = self._get_month_expenses(current_year, current_month, start_of_month, self.current_date)
        current_savings = current_month_income - current_month_expenses
        
        # Saldo do mês passado (proporcional aos dias)
        if current_month == 1:
            prev_month = 12
            prev_year = current_year - 1
        else:
            prev_month = current_month - 1
            prev_year = current_year
        
        days_in_current_month = self.current_date.day
        prev_month_start = date(prev_year, prev_month, 1)
        prev_month_end = date(prev_year, prev_month, min(days_in_current_month, 28))  # Evitar problemas com dias do mês
        
        prev_month_income = self._get_month_income(prev_year, prev_month, prev_month_start, prev_month_end)
        prev_month_expenses = self._get_month_expenses(prev_year, prev_month, prev_month_start, prev_month_end)
        prev_savings = prev_month_income - prev_month_expenses
        
        # Se está economizando mais que o mês passado
        if current_savings > prev_savings and prev_savings > 0:
            improvement = current_savings - prev_savings
            alert = Alert(
                alert_type=AlertType.POSITIVE_TREND,
                priority=AlertPriority.LOW,
                title="Parabéns! Economia melhorou",
                message=f"Você está economizando {self._format_currency(improvement)} a mais "
                       f"que no mês passado. Continue assim!",
                data={
                    'current_savings': current_savings,
                    'previous_savings': prev_savings,
                    'improvement': improvement,
                    'improvement_percentage': ((current_savings / prev_savings) - 1) * 100 if prev_savings > 0 else 0
                },
                action_url="/dashboard"
            )
            self.alerts.append(alert)
    
    def get_alerts_by_priority(self, priority: AlertPriority) -> List[Alert]:
        """Retorna alertas filtrados por prioridade"""
        return [alert for alert in self.alerts if alert.priority == priority]
    
    def get_unread_alerts_count(self) -> int:
        """Retorna o número de alertas não lidos"""
        return len([alert for alert in self.alerts if not alert.is_read])
    
    def mark_alert_as_read(self, alert_index: int):
        """Marca um alerta como lido"""
        if 0 <= alert_index < len(self.alerts):
            self.alerts[alert_index].is_read = True
    
    def get_alerts_summary(self) -> Dict:
        """Retorna um resumo dos alertas"""
        total = len(self.alerts)
        by_priority = {
            'critical': len(self.get_alerts_by_priority(AlertPriority.CRITICAL)),
            'high': len(self.get_alerts_by_priority(AlertPriority.HIGH)),
            'medium': len(self.get_alerts_by_priority(AlertPriority.MEDIUM)),
            'low': len(self.get_alerts_by_priority(AlertPriority.LOW))
        }
        unread = self.get_unread_alerts_count()
        
        return {
            'total': total,
            'unread': unread,
            'by_priority': by_priority,
            'alerts': [alert.to_dict() for alert in self.alerts]
        }
    
    # Métodos auxiliares
    
    def _format_currency(self, amount: float) -> str:
        """Formata valor como moeda"""
        return f"R$ {amount:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    
    def _calculate_total_months(self, goal: Goal) -> float:
        """Calcula o total de meses desde a criação da meta até o prazo"""
        total_days = (goal.target_date - goal.created_at.date()).days
        return max(1, total_days / 30.44)
    
    def _get_month_income(self, year: int, month: int, start_date: date, end_date: date) -> float:
        """Obtém a receita de um período específico"""
        income = db.session.query(
            func.sum(Transaction.amount)
        ).filter(
            and_(
                Transaction.transaction_date >= start_date,
                Transaction.transaction_date <= end_date,
                Transaction.transaction_type == TransactionType.INCOME
            )
        ).scalar()
        return float(income) if income else 0.0
    
    def _get_month_expenses(self, year: int, month: int, start_date: date, end_date: date) -> float:
        """Obtém as despesas de um período específico"""
        expenses = db.session.query(
            func.sum(Transaction.amount)
        ).filter(
            and_(
                Transaction.transaction_date >= start_date,
                Transaction.transaction_date <= end_date,
                Transaction.transaction_type == TransactionType.EXPENSE
            )
        ).scalar()
        return float(expenses) if expenses else 0.0

