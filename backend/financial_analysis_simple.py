from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from sqlalchemy import func, and_, extract
from src.models.financial import (
    Transaction, Category, Account, Goal, SpendingLimit, 
    RecurringTransaction, TransactionType, db
)
from typing import Dict, List, Tuple, Optional
import calendar

class FinancialAnalyzer:
    """Analisador financeiro simplificado sem dependências externas"""
    
    def __init__(self):
        self.current_date = date.today()
    
    def get_dashboard_data(self) -> Dict:
        """Retorna dados consolidados para o dashboard"""
        current_month_summary = self.get_current_month_summary()
        health_score = self.calculate_health_score()
        savings_capacity = self.calculate_savings_capacity(3)
        income_projections = self.calculate_income_projections(3)
        expense_projections = self.calculate_expense_projections(3)
        goals_progress = self.get_goals_progress()
        spending_limits_status = self.get_spending_limits_status()
        
        return {
            'current_month_summary': current_month_summary,
            'health_score': health_score,
            'savings_capacity': savings_capacity,
            'income_projections': income_projections,
            'expense_projections': expense_projections,
            'goals_progress': goals_progress,
            'spending_limits_status': spending_limits_status
        }
    
    def get_current_month_summary(self) -> Dict:
        """Calcula resumo do mês atual"""
        current_month = self.current_date.month
        current_year = self.current_date.year
        
        # Primeiro e último dia do mês
        start_of_month = date(current_year, current_month, 1)
        end_of_month = date(current_year, current_month, calendar.monthrange(current_year, current_month)[1])
        
        # Receitas do mês
        total_income = db.session.query(
            func.sum(Transaction.amount)
        ).filter(
            and_(
                Transaction.transaction_date >= start_of_month,
                Transaction.transaction_date <= self.current_date,
                Transaction.transaction_type == TransactionType.INCOME
            )
        ).scalar() or 0.0
        
        # Despesas do mês
        total_expenses = db.session.query(
            func.sum(Transaction.amount)
        ).filter(
            and_(
                Transaction.transaction_date >= start_of_month,
                Transaction.transaction_date <= self.current_date,
                Transaction.transaction_type == TransactionType.EXPENSE
            )
        ).scalar() or 0.0
        
        # Despesas por categoria
        expenses_by_category = {}
        category_expenses = db.session.query(
            Category.name,
            func.sum(Transaction.amount)
        ).join(Transaction).filter(
            and_(
                Transaction.transaction_date >= start_of_month,
                Transaction.transaction_date <= self.current_date,
                Transaction.transaction_type == TransactionType.EXPENSE
            )
        ).group_by(Category.name).all()
        
        for category_name, amount in category_expenses:
            expenses_by_category[category_name] = float(amount) if amount else 0.0
        
        # Saldo parcial
        partial_balance = total_income - total_expenses
        
        # Período
        period = f"{start_of_month.strftime('%d/%m/%Y')} - {self.current_date.strftime('%d/%m/%Y')}"
        
        return {
            'period': period,
            'total_income': float(total_income),
            'total_expenses': float(total_expenses),
            'expenses_by_category': expenses_by_category,
            'partial_balance': partial_balance,
            'days_in_month': self.current_date.day,
            'total_days_in_month': calendar.monthrange(current_year, current_month)[1]
        }
    
    def calculate_health_score(self) -> Dict:
        """Calcula score de saúde financeira"""
        current_month_data = self.get_current_month_summary()
        
        # Fatores do score
        score_factors = {
            'positive_balance': 0,
            'savings_capacity': 0,
            'spending_discipline': 0,
            'income_diversification': 0
        }
        
        # Saldo positivo (25 pontos)
        if current_month_data['partial_balance'] > 0:
            score_factors['positive_balance'] = 25.0
        
        # Capacidade de poupança (30 pontos)
        if current_month_data['total_income'] > 0:
            savings_rate = current_month_data['partial_balance'] / current_month_data['total_income']
            if savings_rate >= 0.2:  # 20% ou mais
                score_factors['savings_capacity'] = 30.0
            elif savings_rate >= 0.1:  # 10-19%
                score_factors['savings_capacity'] = 20.0
            elif savings_rate > 0:  # Positivo
                score_factors['savings_capacity'] = 10.0
        
        # Disciplina nos gastos (30 pontos)
        limits_status = self.get_spending_limits_status()
        if limits_status:
            within_limits = sum(1 for limit in limits_status if limit['current_spent'] <= limit['monthly_limit'])
            discipline_score = (within_limits / len(limits_status)) * 30
            score_factors['spending_discipline'] = discipline_score
        else:
            score_factors['spending_discipline'] = 15  # Score médio se não há limites
        
        # Diversificação de renda (15 pontos)
        income_sources = db.session.query(Category.name).join(Transaction).filter(
            Transaction.transaction_type == TransactionType.INCOME
        ).distinct().count()
        
        if income_sources >= 3:
            score_factors['income_diversification'] = 15.0
        elif income_sources == 2:
            score_factors['income_diversification'] = 10.0
        elif income_sources == 1:
            score_factors['income_diversification'] = 5.0
        
        total_score = sum(score_factors.values())
        
        # Determinar nível de saúde
        if total_score >= 80:
            health_level = "Excelente"
        elif total_score >= 60:
            health_level = "Boa"
        elif total_score >= 40:
            health_level = "Regular"
        else:
            health_level = "Ruim"
        
        # Recomendações
        recommendations = []
        if score_factors['positive_balance'] == 0:
            recommendations.append("Procure reduzir despesas ou aumentar receitas para manter saldo positivo")
        if score_factors['savings_capacity'] < 20:
            recommendations.append("Procure aumentar sua renda ou reduzir despesas para melhorar a capacidade de poupança")
        if score_factors['spending_discipline'] < 20:
            recommendations.append("Revise e ajuste seus limites de gastos por categoria")
        if score_factors['income_diversification'] < 10:
            recommendations.append("Considere diversificar suas fontes de renda")
        
        if not recommendations:
            recommendations.append("Continue mantendo seus bons hábitos financeiros!")
        
        return {
            'total_score': total_score,
            'health_level': health_level,
            'score_factors': score_factors,
            'recommendations': recommendations
        }
    
    def calculate_savings_capacity(self, months: int) -> Dict:
        """Calcula capacidade de poupança para os próximos meses"""
        results = {}
        
        for i in range(months):
            future_date = self.current_date + relativedelta(months=i+1)
            month_key = f"{future_date.year}-{future_date.month:02d}"
            
            # Projeção baseada na média dos últimos 3 meses
            projected_income = self._calculate_projected_income(future_date)
            projected_expenses = self._calculate_projected_expenses(future_date)
            projected_savings = projected_income - projected_expenses
            
            savings_rate = (projected_savings / projected_income * 100) if projected_income > 0 else 0
            
            results[month_key] = {
                'month': calendar.month_name[future_date.month],
                'year': future_date.year,
                'projected_income': projected_income,
                'projected_expenses': projected_expenses,
                'projected_savings': projected_savings,
                'savings_rate': savings_rate
            }
        
        return results
    
    def calculate_income_projections(self, months: int) -> Dict:
        """Calcula projeções de receita"""
        results = {}
        
        for i in range(months):
            future_date = self.current_date + relativedelta(months=i+1)
            month_key = f"{future_date.year}-{future_date.month:02d}"
            
            projected_income = self._calculate_projected_income(future_date)
            recurring_income = self._calculate_recurring_income(future_date)
            historical_average = self._calculate_historical_income_average()
            
            results[month_key] = {
                'month': future_date.month,
                'month_name': calendar.month_name[future_date.month],
                'year': future_date.year,
                'projected_total': projected_income,
                'recurring_income': recurring_income,
                'historical_average': historical_average
            }
        
        return results
    
    def calculate_expense_projections(self, months: int) -> Dict:
        """Calcula projeções de despesas"""
        results = {}
        
        for i in range(months):
            future_date = self.current_date + relativedelta(months=i+1)
            month_key = f"{future_date.year}-{future_date.month:02d}"
            
            projected_expenses = self._calculate_projected_expenses(future_date)
            recurring_expenses = self._calculate_recurring_expenses(future_date)
            historical_average = self._calculate_historical_expense_average()
            
            # Projeção por categoria
            projected_by_category = self._calculate_projected_expenses_by_category(future_date)
            
            results[month_key] = {
                'month': future_date.month,
                'month_name': calendar.month_name[future_date.month],
                'year': future_date.year,
                'projected_total': projected_expenses,
                'recurring_expenses': recurring_expenses,
                'historical_average': historical_average,
                'projected_by_category': projected_by_category
            }
        
        return results
    
    def get_goals_progress(self) -> List[Dict]:
        """Retorna progresso das metas"""
        goals = db.session.query(Goal).filter(Goal.is_active == True).all()
        
        results = []
        for goal in goals:
            progress_percentage = (goal.current_amount / goal.target_amount * 100) if goal.target_amount > 0 else 0
            remaining_amount = goal.target_amount - goal.current_amount
            days_remaining = (goal.target_date - self.current_date).days
            months_remaining = max(0, days_remaining / 30.44)
            
            monthly_needed = remaining_amount / months_remaining if months_remaining > 0 else remaining_amount
            
            results.append({
                'id': goal.id,
                'name': goal.name,
                'description': goal.description,
                'target_amount': goal.target_amount,
                'current_amount': goal.current_amount,
                'target_date': goal.target_date.isoformat(),
                'progress_percentage': progress_percentage,
                'remaining_amount': remaining_amount,
                'days_remaining': days_remaining,
                'months_remaining': months_remaining,
                'monthly_needed': monthly_needed
            })
        
        return results
    
    def get_spending_limits_status(self) -> List[Dict]:
        """Retorna status dos limites de gastos"""
        current_month = self.current_date.month
        current_year = self.current_date.year
        month_year = f"{current_year}-{current_month:02d}"
        
        limits = db.session.query(SpendingLimit).filter(
            SpendingLimit.month_year == month_year
        ).all()
        
        results = []
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
            
            results.append({
                'category_id': limit.category_id,
                'category_name': limit.category.name,
                'category': {
                    'name': limit.category.name,
                    'color': limit.category.color
                },
                'monthly_limit': limit.monthly_limit,
                'current_spent': float(current_spent),
                'remaining': limit.monthly_limit - current_spent,
                'percentage_used': (current_spent / limit.monthly_limit * 100) if limit.monthly_limit > 0 else 0
            })
        
        return results
    
    # Métodos auxiliares
    
    def _calculate_projected_income(self, target_date: date) -> float:
        """Calcula receita projetada baseada na média histórica"""
        historical_avg = self._calculate_historical_income_average()
        recurring_income = self._calculate_recurring_income(target_date)
        
        # Usar o maior valor entre média histórica e receitas recorrentes
        return max(historical_avg, recurring_income)
    
    def _calculate_projected_expenses(self, target_date: date) -> float:
        """Calcula despesas projetadas baseadas na média histórica"""
        historical_avg = self._calculate_historical_expense_average()
        recurring_expenses = self._calculate_recurring_expenses(target_date)
        
        # Usar o maior valor entre média histórica e despesas recorrentes
        return max(historical_avg, recurring_expenses)
    
    def _calculate_historical_income_average(self) -> float:
        """Calcula média histórica de receitas dos últimos 3 meses"""
        three_months_ago = self.current_date - relativedelta(months=3)
        
        avg_income = db.session.query(
            func.avg(Transaction.amount)
        ).filter(
            and_(
                Transaction.transaction_date >= three_months_ago,
                Transaction.transaction_date <= self.current_date,
                Transaction.transaction_type == TransactionType.INCOME
            )
        ).scalar()
        
        return float(avg_income) if avg_income else 0.0
    
    def _calculate_historical_expense_average(self) -> float:
        """Calcula média histórica de despesas dos últimos 3 meses"""
        three_months_ago = self.current_date - relativedelta(months=3)
        
        avg_expenses = db.session.query(
            func.avg(Transaction.amount)
        ).filter(
            and_(
                Transaction.transaction_date >= three_months_ago,
                Transaction.transaction_date <= self.current_date,
                Transaction.transaction_type == TransactionType.EXPENSE
            )
        ).scalar()
        
        return float(avg_expenses) if avg_expenses else 0.0
    
    def _calculate_recurring_income(self, target_date: date) -> float:
        """Calcula receitas recorrentes para um mês específico"""
        recurring_transactions = db.session.query(RecurringTransaction).filter(
            and_(
                RecurringTransaction.is_active == True,
                RecurringTransaction.transaction_type == TransactionType.INCOME
            )
        ).all()
        
        total = 0.0
        for transaction in recurring_transactions:
            # Simplificação: assumir que todas as transações recorrentes ocorrem mensalmente
            total += transaction.amount
        
        return total
    
    def _calculate_recurring_expenses(self, target_date: date) -> float:
        """Calcula despesas recorrentes para um mês específico"""
        recurring_transactions = db.session.query(RecurringTransaction).filter(
            and_(
                RecurringTransaction.is_active == True,
                RecurringTransaction.transaction_type == TransactionType.EXPENSE
            )
        ).all()
        
        total = 0.0
        for transaction in recurring_transactions:
            # Simplificação: assumir que todas as transações recorrentes ocorrem mensalmente
            total += transaction.amount
        
        return total
    
    def _calculate_projected_expenses_by_category(self, target_date: date) -> Dict[str, float]:
        """Calcula despesas projetadas por categoria"""
        categories = db.session.query(Category).all()
        projections = {}
        
        for category in categories:
            # Média histórica da categoria nos últimos 3 meses
            three_months_ago = self.current_date - relativedelta(months=3)
            
            avg_expense = db.session.query(
                func.avg(Transaction.amount)
            ).filter(
                and_(
                    Transaction.category_id == category.id,
                    Transaction.transaction_date >= three_months_ago,
                    Transaction.transaction_date <= self.current_date,
                    Transaction.transaction_type == TransactionType.EXPENSE
                )
            ).scalar()
            
            projections[category.name] = float(avg_expense) if avg_expense else 0.0
        
        return projections

