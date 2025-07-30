from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from src.services.file_import import FileImportService
import os

import_bp = Blueprint('import', __name__)

@import_bp.route('/upload-transactions', methods=['POST'])
def upload_transactions():
    """Endpoint para upload e importação de transações via arquivo"""
    try:
        # Verificar se arquivo foi enviado
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'error': 'Nenhum arquivo foi enviado'
            }), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': 'Nenhum arquivo foi selecionado'
            }), 400
        
        # Processar arquivo
        import_service = FileImportService()
        result = import_service.import_transactions_from_file(file)
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Erro interno do servidor: {str(e)}'
        }), 500

@import_bp.route('/template', methods=['GET'])
def get_import_template():
    """Retorna template/exemplo para importação"""
    try:
        import_service = FileImportService()
        template = import_service.get_import_template()
        
        return jsonify({
            'success': True,
            'data': template
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Erro ao obter template: {str(e)}'
        }), 500

@import_bp.route('/download-template', methods=['GET'])
def download_template():
    """Gera e retorna um arquivo CSV template para download"""
    try:
        import csv
        import io
        from flask import make_response
        
        # Criar CSV template
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow(['data', 'descricao', 'valor', 'tipo', 'categoria', 'conta', 'observacoes'])
        
        # Exemplos
        writer.writerow(['01/01/2025', 'Salário Janeiro', '5000.00', 'receita', 'Salário', 'Conta Corrente', 'Pagamento mensal'])
        writer.writerow(['02/01/2025', 'Supermercado Extra', '-250.50', 'despesa', 'Alimentação', 'Cartão de Crédito', 'Compras da semana'])
        writer.writerow(['03/01/2025', 'Freelance Design', '800.00', 'receita', 'Freelance', 'Conta Corrente', 'Projeto logo empresa'])
        writer.writerow(['04/01/2025', 'Uber', '-25.50', 'despesa', 'Transporte', 'Cartão de Débito', 'Ida ao trabalho'])
        writer.writerow(['05/01/2025', 'Netflix', '-32.90', 'despesa', 'Lazer', 'Cartão de Crédito', 'Assinatura mensal'])
        
        # Preparar resposta
        output.seek(0)
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        response.headers['Content-Disposition'] = 'attachment; filename=template_importacao_transacoes.csv'
        
        return response
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Erro ao gerar template: {str(e)}'
        }), 500

@import_bp.route('/validate-file', methods=['POST'])
def validate_file():
    """Valida arquivo antes da importação (preview)"""
    try:
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'error': 'Nenhum arquivo foi enviado'
            }), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': 'Nenhum arquivo foi selecionado'
            }), 400
        
        import_service = FileImportService()
        
        # Validar arquivo
        validation_result = import_service._validate_file(file)
        if not validation_result['valid']:
            return jsonify({
                'success': False,
                'error': validation_result['error']
            }), 400
        
        # Processar arquivo para preview
        file_extension = import_service._get_file_extension(file.filename)
        
        if file_extension == '.csv':
            data = import_service._process_csv_file(file)
        else:
            data = import_service._process_excel_file(file)
        
        # Validar estrutura
        structure_validation = import_service._validate_data_structure(data)
        if not structure_validation['valid']:
            return jsonify({
                'success': False,
                'error': structure_validation['error']
            }), 400
        
        # Retornar preview (primeiras 5 linhas)
        preview_data = data[:5] if len(data) > 5 else data
        
        # Remover campo interno _row_number do preview
        for row in preview_data:
            row.pop('_row_number', None)
        
        return jsonify({
            'success': True,
            'data': {
                'total_rows': len(data),
                'preview': preview_data,
                'columns_found': list(data[0].keys()) if data else [],
                'required_columns': import_service.required_columns,
                'optional_columns': import_service.optional_columns
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Erro ao validar arquivo: {str(e)}'
        }), 500

