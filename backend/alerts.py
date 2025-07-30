from flask import Blueprint, request, jsonify
from src.services.alert_system import AlertSystem, AlertPriority, AlertType

alerts_bp = Blueprint('alerts', __name__)

# Instância do sistema de alertas
alert_system = AlertSystem()

@alerts_bp.route('/alerts', methods=['GET'])
def get_alerts():
    """Endpoint para obter todos os alertas"""
    try:
        priority_filter = request.args.get('priority')
        alert_type_filter = request.args.get('type')
        unread_only = request.args.get('unread_only', 'false').lower() == 'true'
        
        # Gerar alertas atualizados
        alerts = alert_system.generate_all_alerts()
        
        # Aplicar filtros
        filtered_alerts = alerts
        
        if priority_filter:
            try:
                priority = AlertPriority(priority_filter)
                filtered_alerts = [alert for alert in filtered_alerts if alert.priority == priority]
            except ValueError:
                return jsonify({'success': False, 'error': 'Prioridade inválida'}), 400
        
        if alert_type_filter:
            try:
                alert_type = AlertType(alert_type_filter)
                filtered_alerts = [alert for alert in filtered_alerts if alert.alert_type == alert_type]
            except ValueError:
                return jsonify({'success': False, 'error': 'Tipo de alerta inválido'}), 400
        
        if unread_only:
            filtered_alerts = [alert for alert in filtered_alerts if not alert.is_read]
        
        # Converter para dicionários
        alerts_data = [alert.to_dict() for alert in filtered_alerts]
        
        return jsonify({
            'success': True,
            'data': {
                'alerts': alerts_data,
                'total': len(alerts_data),
                'summary': alert_system.get_alerts_summary()
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@alerts_bp.route('/alerts/summary', methods=['GET'])
def get_alerts_summary():
    """Endpoint para obter resumo dos alertas"""
    try:
        # Gerar alertas atualizados
        alert_system.generate_all_alerts()
        
        summary = alert_system.get_alerts_summary()
        
        return jsonify({
            'success': True,
            'data': summary
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@alerts_bp.route('/alerts/<int:alert_index>/mark-read', methods=['POST'])
def mark_alert_read(alert_index):
    """Endpoint para marcar um alerta como lido"""
    try:
        alert_system.mark_alert_as_read(alert_index)
        
        return jsonify({
            'success': True,
            'message': 'Alerta marcado como lido'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@alerts_bp.route('/alerts/priority/<priority>', methods=['GET'])
def get_alerts_by_priority(priority):
    """Endpoint para obter alertas por prioridade"""
    try:
        try:
            priority_enum = AlertPriority(priority)
        except ValueError:
            return jsonify({'success': False, 'error': 'Prioridade inválida'}), 400
        
        # Gerar alertas atualizados
        alert_system.generate_all_alerts()
        
        alerts = alert_system.get_alerts_by_priority(priority_enum)
        alerts_data = [alert.to_dict() for alert in alerts]
        
        return jsonify({
            'success': True,
            'data': {
                'alerts': alerts_data,
                'total': len(alerts_data),
                'priority': priority
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@alerts_bp.route('/alerts/types', methods=['GET'])
def get_alert_types():
    """Endpoint para obter tipos de alertas disponíveis"""
    try:
        types = [
            {
                'value': alert_type.value,
                'name': alert_type.name,
                'description': _get_alert_type_description(alert_type)
            }
            for alert_type in AlertType
        ]
        
        priorities = [
            {
                'value': priority.value,
                'name': priority.name,
                'description': _get_priority_description(priority)
            }
            for priority in AlertPriority
        ]
        
        return jsonify({
            'success': True,
            'data': {
                'types': types,
                'priorities': priorities
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@alerts_bp.route('/alerts/test', methods=['POST'])
def generate_test_alerts():
    """Endpoint para gerar alertas de teste (apenas para desenvolvimento)"""
    try:
        from src.services.alert_system import Alert
        
        # Limpar alertas existentes
        alert_system.alerts = []
        
        # Criar alguns alertas de teste
        test_alerts = [
            Alert(
                alert_type=AlertType.SPENDING_LIMIT_EXCEEDED,
                priority=AlertPriority.HIGH,
                title="Teste: Limite excedido",
                message="Este é um alerta de teste para limite excedido.",
                data={'category': 'Alimentação', 'limit': 1000, 'spent': 1200},
                action_url="/transactions"
            ),
            Alert(
                alert_type=AlertType.GOAL_DEADLINE_APPROACHING,
                priority=AlertPriority.MEDIUM,
                title="Teste: Meta próxima do prazo",
                message="Este é um alerta de teste para meta próxima do prazo.",
                data={'goal': 'Viagem', 'days_remaining': 15},
                action_url="/goals"
            ),
            Alert(
                alert_type=AlertType.POSITIVE_TREND,
                priority=AlertPriority.LOW,
                title="Teste: Tendência positiva",
                message="Este é um alerta de teste para tendência positiva.",
                data={'improvement': 500},
                action_url="/dashboard"
            )
        ]
        
        alert_system.alerts.extend(test_alerts)
        
        return jsonify({
            'success': True,
            'message': f'{len(test_alerts)} alertas de teste criados',
            'data': {
                'alerts': [alert.to_dict() for alert in test_alerts]
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def _get_alert_type_description(alert_type: AlertType) -> str:
    """Retorna descrição do tipo de alerta"""
    descriptions = {
        AlertType.SPENDING_LIMIT_WARNING: "Aviso de aproximação do limite de gastos",
        AlertType.SPENDING_LIMIT_EXCEEDED: "Limite de gastos excedido",
        AlertType.GOAL_BEHIND_SCHEDULE: "Meta atrasada em relação ao cronograma",
        AlertType.GOAL_DEADLINE_APPROACHING: "Prazo da meta se aproximando",
        AlertType.LOW_BALANCE_PROJECTION: "Projeção de saldo baixo ou negativo",
        AlertType.UNUSUAL_SPENDING: "Gastos incomuns detectados",
        AlertType.BILL_REMINDER: "Lembrete de conta a pagar",
        AlertType.POSITIVE_TREND: "Tendência positiva na economia"
    }
    return descriptions.get(alert_type, "Tipo de alerta desconhecido")

def _get_priority_description(priority: AlertPriority) -> str:
    """Retorna descrição da prioridade"""
    descriptions = {
        AlertPriority.LOW: "Baixa - Informativo",
        AlertPriority.MEDIUM: "Média - Requer atenção",
        AlertPriority.HIGH: "Alta - Ação recomendada",
        AlertPriority.CRITICAL: "Crítica - Ação imediata necessária"
    }
    return descriptions.get(priority, "Prioridade desconhecida")

