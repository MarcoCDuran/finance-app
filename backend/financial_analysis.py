from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from sqlalchemy import func, and_, extract
from src.models.financial import (
    Transaction, Category, Account, Goal, SpendingLimit, 
    RecurringTransaction, TransactionType, db
)
import pandas as pd
from typing import Dict, List, Tuple, Optional

class FinancialAnalyzer:
    """Classe responsável por análises e projeções financeiras"""
    
    def __init__(self):
        self.current_date = date.today()
        self.current_month = self.current_date.month
        self.current_year = self.current_date.year
    
    def get_current_month_summary(self) -> Dict:
        """Retorna o resumo financeiro do mês corrente"""
        start_of_month = date(self.current_year, self.current_month, 1)
        
        # Despesas do mês corrente por categoria
        expenses_query = db.session.query(
            Category.name,
            func.sum(Transaction.amount).label('total')
        ).join(Transaction).filter(
            and_(
                Transaction.transaction_date >= start_of_month,
                Transaction.transaction_date <= self.current_date,
                Transaction.transaction_type == TransactionType.EXPENSE
            )
        ).group_by(Category.id, Category.name).all()
        
        expenses_by_category = {exp.name: float(exp.total) for exp in expenses_query}
        total_expenses = sum(expenses_by_category.values())
        
        # Receitas do mês corrente
        income_query = db.session.query(
            func.sum(Transaction.amount).label('total')
        ).filter(
            and_(
                Transaction.transaction_date >= start_of_month,
                Transaction.transaction_date <= self.current_date,
                Transaction.transaction_type == TransactionType.INCOME
            )
        ).scalar()
        
        total_income = float(income_query) if income_query else 0.0
        
        # Saldo parcial
        partial_balance = total_income - total_expenses
        
        return {
            'period': f"{start_of_month.strftime('%d/%m/%Y')} - {self.current_date.strftime('%d/%m/%Y')}",
            'total_income': total_income,
            'total_expenses': total_expenses,
            'expenses_by_category': expenses_by_category,
            'partial_balance': partial_balance,
            'days_in_month': self.current_date.day,
            'total_days_in_month': self._get_days_in_month(self.current_year, self.current_month)
        }
    
    def get_spending_limits_status(self) -> List[Dict]:
        """Retorna o status dos limites de gastos por categoria"""
        month_year = f"{self.current_year}-{self.current_month:02d}"
        
        limits = db.session.query(SpendingLimit).filter(
            SpendingLimit.month_year == month_year
        ).all()
        
        status_list = []
        for limit in limits:
            # Calcular gastos atuais da categoria no mês
            start_of_month = date(self.current_year, self.current_month, 1)
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
            remaining = limit.monthly_limit - current_spent
            
            status_list.append({
                'category_name': limit.category.name,
                'monthly_limit': limit.monthly_limit,
                'current_spent': float(current_spent),
                'remaining': remaining,
                'percentage_used': percentage_used,
                'is_over_limit': current_spent > limit.monthly_limit
            })
        
        return status_list
    
    def project_future_expenses(self, months_ahead: int = 3) -> Dict:
        """Projeta despesas futuras baseadas no histórico e transações recorrentes"""
        projections = {}
        
        for month_offset in range(1, months_ahead + 1):
            target_date = self.current_date + relativedelta(months=month_offset)
            target_month = target_date.month
            target_year = target_date.year
            
            # Projeção baseada em transações recorrentes
            recurring_expenses = self._get_recurring_expenses_for_month(target_year, target_month)
            
            # Projeção baseada na média histórica (últimos 6 meses)
            historical_avg = self._get_historical_average_expenses(target_month)
            
            # Combinar projeções
            projected_expenses = self._combine_projections(recurring_expenses, historical_avg)
            
            projections[f"{target_year}-{target_month:02d}"] = {
                'year': target_year,
                'month': target_month,
                'month_name': target_date.strftime('%B'),
                'recurring_expenses': recurring_expenses,
                'historical_average': historical_avg,
                'projected_total': projected_expenses,
                'projected_by_category': self._project_expenses_by_category(target_year, target_month)
            }
        
        return projections
    
    def project_future_income(self, months_ahead: int = 3) -> Dict:
        """Projeta receitas futuras baseadas em receitas recorrentes e histórico"""
        projections = {}
        
        for month_offset in range(1, months_ahead + 1):
            target_date = self.current_date + relativedelta(months=month_offset)
            target_month = target_date.month
            target_year = target_date.year
            
            # Receitas recorrentes
            recurring_income = self._get_recurring_income_for_month(target_year, target_month)
            
            # Média histórica de receitas
            historical_avg_income = self._get_historical_average_income(target_month)
            
            projected_income = max(recurring_income, historical_avg_income)
            
            projections[f"{target_year}-{target_month:02d}"] = {
                'year': target_year,
                'month': target_month,
                'month_name': target_date.strftime('%B'),
                'recurring_income': recurring_income,
                'historical_average': historical_avg_income,
                'projected_total': projected_income
            }
        
        return projections
    
    def calculate_savings_capacity(self, months_ahead: int = 3) -> Dict:
        """Calcula a capacidade de poupança baseada nas projeções"""
        expense_projections = self.project_future_expenses(months_ahead)
        income_projections = self.project_future_income(months_ahead)
        
        savings_capacity = {}
        
        for month_key in expense_projections.keys():
            projected_income = income_projections[month_key]['projected_total']
            projected_expenses = expense_projections[month_key]['projected_total']
            
            monthly_savings = projected_income - projected_expenses
            
            savings_capacity[month_key] = {
                'month': expense_projections[month_key]['month_name'],
                'year': expense_projections[month_key]['year'],
                'projected_income': projected_income,
                'projected_expenses': projected_expenses,
                'projected_savings': monthly_savings,
                'savings_rate': (monthly_savings / projected_income * 100) if projected_income > 0 else 0
            }
        
        return savings_capacity
    
    def analyze_goals_progress(self) -> List[Dict]:
        """Analisa o progresso das metas de economia"""
        goals = db.session.query(Goal).filter(Goal.is_active == True).all()
        goals_analysis = []
        
        for goal in goals:
            days_remaining = (goal.target_date - self.current_date).days
            months_remaining = max(1, days_remaining / 30.44)  # Média de dias por mês
            
            amount_needed = goal.target_amount - goal.current_amount
            monthly_savings_needed = amount_needed / months_remaining if months_remaining > 0 else amount_needed
            
            # Verificar capacidade de poupança
            savings_capacity = self.calculate_savings_capacity(3)
            avg_monthly_savings = sum([s['projected_savings'] for s in savings_capacity.values()]) / len(savings_capacity)
            
            is_achievable = monthly_savings_needed <= avg_monthly_savings
            
            goals_analysis.append({
                'id': goal.id,
                'name': goal.name,
                'description': goal.description,
                'target_amount': goal.target_amount,
                'current_amount': goal.current_amount,
                'amount_needed': amount_needed,
                'target_date': goal.target_date.isoformat(),
                'days_remaining': days_remaining,
                'months_remaining': round(months_remaining, 1),
                'monthly_savings_needed': monthly_savings_needed,
                'progress_percentage': (goal.current_amount / goal.target_amount * 100) if goal.target_amount > 0 else 0,
                'is_achievable': is_achievable,
                'avg_monthly_savings_capacity': avg_monthly_savings
            })
        
        return goals_analysis
    
    def get_financial_health_score(self) -> Dict:
        """Calcula um score de saúde financeira baseado em vários fatores"""
        current_summary = self.get_current_month_summary()
        spending_limits = self.get_spending_limits_status()
        savings_capacity = self.calculate_savings_capacity(1)
        
        # Fatores para o score (0-100)
        score_factors = {}
        
        # 1. Saldo positivo (25 pontos)
        if current_summary['partial_balance'] > 0:
            score_factors['positive_balance'] = 25
        else:
            score_factors['positive_balance'] = max(0, 25 + (current_summary['partial_balance'] / 1000) * 5)
        
        # 2. Respeito aos limites de gastos (25 pontos)
        if spending_limits:
            over_limit_count = sum(1 for limit in spending_limits if limit['is_over_limit'])
            score_factors['spending_discipline'] = max(0, 25 - (over_limit_count * 10))
        else:
            score_factors['spending_discipline'] = 15  # Score neutro se não há limites definidos
        
        # 3. Capacidade de poupança (25 pontos)
        if savings_capacity:
            next_month_savings = list(savings_capacity.values())[0]['projected_savings']
            if next_month_savings > 0:
                score_factors['savings_capacity'] = min(25, (next_month_savings / 1000) * 5)
            else:
                score_factors['savings_capacity'] = 0
        else:
            score_factors['savings_capacity'] = 0
        
        # 4. Diversificação de receitas (25 pontos)
        income_sources = self._count_income_sources()
        score_factors['income_diversification'] = min(25, income_sources * 8)
        
        total_score = sum(score_factors.values())
        
        return {
            'total_score': round(total_score, 1),
            'score_factors': score_factors,
            'health_level': self._get_health_level(total_score),
            'recommendations': self._get_health_recommendations(score_factors)
        }
    
    # Métodos auxiliares privados
    
    def _get_days_in_month(self, year: int, month: int) -> int:
        """Retorna o número de dias no mês"""
        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)
        last_day = next_month - timedelta(days=1)
        return last_day.day
    
    def _get_recurring_expenses_for_month(self, year: int, month: int) -> float:
        """Calcula despesas recorrentes para um mês específico"""
        target_date = date(year, month, 1)
        
        recurring_transactions = db.session.query(RecurringTransaction).filter(
            and_(
                RecurringTransaction.is_active == True,
                RecurringTransaction.transaction_type == TransactionType.EXPENSE,
                RecurringTransaction.start_date <= target_date,
                db.or_(
                    RecurringTransaction.end_date.is_(None),
                    RecurringTransaction.end_date >= target_date
                )
            )
        ).all()
        
        total = 0.0
        for transaction in recurring_transactions:
            if self._should_occur_in_month(transaction, year, month):
                total += transaction.amount
        
        return total
    
    def _get_recurring_income_for_month(self, year: int, month: int) -> float:
        """Calcula receitas recorrentes para um mês específico"""
        target_date = date(year, month, 1)
        
        recurring_transactions = db.session.query(RecurringTransaction).filter(
            and_(
                RecurringTransaction.is_active == True,
                RecurringTransaction.transaction_type == TransactionType.INCOME,
                RecurringTransaction.start_date <= target_date,
                db.or_(
                    RecurringTransaction.end_date.is_(None),
                    RecurringTransaction.end_date >= target_date
                )
            )
        ).all()
        
        total = 0.0
        for transaction in recurring_transactions:
            if self._should_occur_in_month(transaction, year, month):
                total += transaction.amount
        
        return total
    
    def _should_occur_in_month(self, recurring_transaction: RecurringTransaction, year: int, month: int) -> bool:
        """Verifica se uma transação recorrente deve ocorrer em um mês específico"""
        if recurring_transaction.frequency == 'monthly':
            return True
        elif recurring_transaction.frequency == 'yearly':
            return recurring_transaction.start_date.month == month
        elif recurring_transaction.frequency == 'weekly':
            # Simplificação: assume que transações semanais ocorrem todo mês
            return True
        return False
    
    def _get_historical_average_expenses(self, target_month: int) -> float:
        """Calcula a média histórica de despesas para um mês específico"""
        # Buscar dados dos últimos 6 meses do mesmo mês
        historical_data = []
        
        for year_offset in range(1, 4):  # Últimos 3 anos
            historical_year = self.current_year - year_offset
            
            total = db.session.query(
                func.sum(Transaction.amount)
            ).filter(
                and_(
                    extract('year', Transaction.transaction_date) == historical_year,
                    extract('month', Transaction.transaction_date) == target_month,
                    Transaction.transaction_type == TransactionType.EXPENSE
                )
            ).scalar()
            
            if total:
                historical_data.append(float(total))
        
        return sum(historical_data) / len(historical_data) if historical_data else 0.0
    
    def _get_historical_average_income(self, target_month: int) -> float:
        """Calcula a média histórica de receitas para um mês específico"""
        historical_data = []
        
        for year_offset in range(1, 4):  # Últimos 3 anos
            historical_year = self.current_year - year_offset
            
            total = db.session.query(
                func.sum(Transaction.amount)
            ).filter(
                and_(
                    extract('year', Transaction.transaction_date) == historical_year,
                    extract('month', Transaction.transaction_date) == target_month,
                    Transaction.transaction_type == TransactionType.INCOME
                )
            ).scalar()
            
            if total:
                historical_data.append(float(total))
        
        return sum(historical_data) / len(historical_data) if historical_data else 0.0
    
    def _combine_projections(self, recurring: float, historical: float) -> float:
        """Combina projeções recorrentes e históricas"""
        # Se há transações recorrentes, usar elas como base e adicionar variação histórica
        if recurring > 0:
            return recurring + (historical * 0.3)  # 30% de variação baseada no histórico
        else:
            return historical
    
    def _project_expenses_by_category(self, year: int, month: int) -> Dict:
        """Projeta despesas por categoria para um mês específico"""
        categories = db.session.query(Category).all()
        projections = {}
        
        for category in categories:
            # Média histórica da categoria
            historical_avg = db.session.query(
                func.avg(Transaction.amount)
            ).filter(
                and_(
                    Transaction.category_id == category.id,
                    Transaction.transaction_type == TransactionType.EXPENSE,
                    extract('month', Transaction.transaction_date) == month
                )
            ).scalar()
            
            projections[category.name] = float(historical_avg) if historical_avg else 0.0
        
        return projections
    
    def _count_income_sources(self) -> int:
        """Conta o número de fontes de renda diferentes"""
        # Simplificação: conta categorias de receita únicas nos últimos 3 meses
        three_months_ago = self.current_date - relativedelta(months=3)
        
        sources = db.session.query(Category.id).join(Transaction).filter(
            and_(
                Transaction.transaction_date >= three_months_ago,
                Transaction.transaction_type == TransactionType.INCOME
            )
        ).distinct().count()
        
        return sources
    
    def _get_health_level(self, score: float) -> str:
        """Retorna o nível de saúde financeira baseado no score"""
        if score >= 80:
            return "Excelente"
        elif score >= 60:
            return "Boa"
        elif score >= 40:
            return "Regular"
        elif score >= 20:
            return "Ruim"
        else:
            return "Crítica"
    
    def _get_health_recommendations(self, score_factors: Dict) -> List[str]:
        """Gera recomendações baseadas nos fatores do score"""
        recommendations = []
        
        if score_factors['positive_balance'] < 15:
            recommendations.append("Reduza gastos desnecessários para manter saldo positivo")
        
        if score_factors['spending_discipline'] < 15:
            recommendations.append("Revise e ajuste seus limites de gastos por categoria")
        
        if score_factors['savings_capacity'] < 10:
            recommendations.append("Procure aumentar sua renda ou reduzir despesas para melhorar a capacidade de poupança")
        
        if score_factors['income_diversification'] < 15:
            recommendations.append("Considere diversificar suas fontes de renda")
        
        if not recommendations:
            recommendations.append("Parabéns! Sua saúde financeira está em bom estado. Continue assim!")
        
        return recommendations

