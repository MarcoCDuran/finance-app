import csv
import io
from datetime import datetime, date
from typing import Dict, List, Tuple, Optional, Union
from werkzeug.datastructures import FileStorage
from src.models.financial import (
    db, Transaction, Category, Account, TransactionType
)
from sqlalchemy import func

class FileImportService:
    """Serviço para importação massiva de transações via CSV/Excel"""
    
    def __init__(self):
        self.supported_formats = ['.csv']  # Apenas CSV para evitar dependência do pandas
        self.required_columns = ['data', 'descricao', 'valor', 'tipo']
        self.optional_columns = ['categoria', 'conta', 'observacoes']
        
    def import_transactions_from_file(self, file: FileStorage) -> Dict:
        """
        Importa transações de um arquivo CSV ou Excel
        
        Args:
            file: Arquivo enviado pelo usuário
            
        Returns:
            Dict com resultado da importação
        """
        try:
            # Validar arquivo
            validation_result = self._validate_file(file)
            if not validation_result['valid']:
                return validation_result
            
            # Processar arquivo CSV
            file_extension = self._get_file_extension(file.filename)
            
            if file_extension == '.csv':
                data = self._process_csv_file(file)
            else:
                return {
                    'success': False,
                    'error': 'Apenas arquivos CSV são suportados no momento',
                    'data': None
                }
            
            # Validar estrutura dos dados
            validation_result = self._validate_data_structure(data)
            if not validation_result['valid']:
                return validation_result
            
            # Processar e inserir transações
            import_result = self._process_transactions(data)
            
            return {
                'success': True,
                'message': f'Importação concluída com sucesso!',
                'data': import_result
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Erro durante a importação: {str(e)}',
                'data': None
            }
    
    def _validate_file(self, file: FileStorage) -> Dict:
        """Valida o arquivo enviado"""
        if not file or not file.filename:
            return {
                'valid': False,
                'error': 'Nenhum arquivo foi enviado'
            }
        
        file_extension = self._get_file_extension(file.filename)
        if file_extension not in self.supported_formats:
            return {
                'valid': False,
                'error': f'Formato de arquivo não suportado. Use: {", ".join(self.supported_formats)}'
            }
        
        # Verificar tamanho do arquivo (máximo 10MB)
        file.seek(0, 2)  # Ir para o final do arquivo
        file_size = file.tell()
        file.seek(0)  # Voltar para o início
        
        if file_size > 10 * 1024 * 1024:  # 10MB
            return {
                'valid': False,
                'error': 'Arquivo muito grande. Tamanho máximo: 10MB'
            }
        
        return {'valid': True}
    
    def _get_file_extension(self, filename: str) -> str:
        """Extrai a extensão do arquivo"""
        return '.' + filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    
    def _process_csv_file(self, file: FileStorage) -> List[Dict]:
        """Processa arquivo CSV"""
        try:
            # Tentar diferentes encodings
            encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
            
            for encoding in encodings:
                try:
                    file.seek(0)
                    content = file.read().decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise ValueError("Não foi possível decodificar o arquivo CSV")
            
            # Detectar delimitador
            sniffer = csv.Sniffer()
            delimiter = sniffer.sniff(content[:1024]).delimiter
            
            # Processar CSV
            csv_reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
            data = []
            
            for row_num, row in enumerate(csv_reader, start=2):
                # Normalizar nomes das colunas (remover espaços, converter para minúsculas)
                normalized_row = {
                    self._normalize_column_name(key): value.strip() if value else ''
                    for key, value in row.items()
                }
                normalized_row['_row_number'] = row_num
                data.append(normalized_row)
            
            return data
            
        except Exception as e:
            raise ValueError(f"Erro ao processar arquivo CSV: {str(e)}")
    
    def _normalize_column_name(self, column_name: str) -> str:
        """Normaliza nomes de colunas para padronização"""
        # Mapeamento de possíveis nomes de colunas
        column_mapping = {
            # Data
            'data': 'data',
            'date': 'data',
            'data_transacao': 'data',
            'data_lancamento': 'data',
            'dt_transacao': 'data',
            'dt_lancamento': 'data',
            
            # Descrição
            'descricao': 'descricao',
            'description': 'descricao',
            'historico': 'descricao',
            'memo': 'descricao',
            'observacao': 'descricao',
            'detalhes': 'descricao',
            
            # Valor
            'valor': 'valor',
            'value': 'valor',
            'amount': 'valor',
            'quantia': 'valor',
            'montante': 'valor',
            
            # Tipo
            'tipo': 'tipo',
            'type': 'tipo',
            'debito_credito': 'tipo',
            'entrada_saida': 'tipo',
            'operacao': 'tipo',
            
            # Categoria
            'categoria': 'categoria',
            'category': 'categoria',
            'classificacao': 'categoria',
            
            # Conta
            'conta': 'conta',
            'account': 'conta',
            'banco': 'conta',
            'cartao': 'conta',
            
            # Observações
            'observacoes': 'observacoes',
            'notes': 'observacoes',
            'comentarios': 'observacoes'
        }
        
        normalized = column_name.lower().strip().replace(' ', '_').replace('-', '_')
        return column_mapping.get(normalized, normalized)
    
    def _validate_data_structure(self, data: List[Dict]) -> Dict:
        """Valida a estrutura dos dados importados"""
        if not data:
            return {
                'valid': False,
                'error': 'Arquivo está vazio ou não contém dados válidos'
            }
        
        # Verificar se as colunas obrigatórias existem
        first_row = data[0]
        missing_columns = []
        
        for required_col in self.required_columns:
            if required_col not in first_row:
                missing_columns.append(required_col)
        
        if missing_columns:
            return {
                'valid': False,
                'error': f'Colunas obrigatórias não encontradas: {", ".join(missing_columns)}. '
                        f'Colunas obrigatórias: {", ".join(self.required_columns)}'
            }
        
        return {'valid': True}
    
    def _process_transactions(self, data: List[Dict]) -> Dict:
        """Processa e insere as transações no banco de dados"""
        results = {
            'total_rows': len(data),
            'successful_imports': 0,
            'failed_imports': 0,
            'errors': [],
            'warnings': []
        }
        
        # Cache para categorias e contas
        categories_cache = self._build_categories_cache()
        accounts_cache = self._build_accounts_cache()
        
        for row in data:
            try:
                transaction_data = self._parse_transaction_row(row, categories_cache, accounts_cache)
                
                if transaction_data:
                    # Criar transação
                    transaction = Transaction(**transaction_data)
                    db.session.add(transaction)
                    results['successful_imports'] += 1
                else:
                    results['failed_imports'] += 1
                    results['errors'].append(f"Linha {row.get('_row_number', '?')}: Dados inválidos")
                    
            except Exception as e:
                results['failed_imports'] += 1
                results['errors'].append(f"Linha {row.get('_row_number', '?')}: {str(e)}")
        
        # Salvar todas as transações
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise ValueError(f"Erro ao salvar transações no banco de dados: {str(e)}")
        
        return results
    
    def _parse_transaction_row(self, row: Dict, categories_cache: Dict, accounts_cache: Dict) -> Optional[Dict]:
        """Converte uma linha do arquivo em dados de transação"""
        try:
            # Parsear data
            transaction_date = self._parse_date(row['data'])
            if not transaction_date:
                raise ValueError("Data inválida")
            
            # Parsear valor
            amount = self._parse_amount(row['valor'])
            if amount is None:
                raise ValueError("Valor inválido")
            
            # Determinar tipo da transação
            transaction_type = self._parse_transaction_type(row['tipo'], amount)
            
            # Obter ou criar categoria
            category_id = self._get_or_create_category(row.get('categoria', 'Outros'), categories_cache)
            
            # Obter ou criar conta
            account_id = self._get_or_create_account(row.get('conta', 'Conta Principal'), accounts_cache)
            
            return {
                'description': row['descricao'][:255] if row['descricao'] else 'Transação importada',
                'amount': abs(amount),  # Sempre positivo, o tipo define se é entrada ou saída
                'transaction_date': transaction_date,
                'transaction_type': transaction_type,
                'category_id': category_id,
                'account_id': account_id,
                'notes': row.get('observacoes', '')[:500] if row.get('observacoes') else None
            }
            
        except Exception as e:
            raise ValueError(str(e))
    
    def _parse_date(self, date_str: str) -> Optional[date]:
        """Converte string de data para objeto date"""
        if not date_str:
            return None
        
        # Formatos de data suportados
        date_formats = [
            '%d/%m/%Y',
            '%d-%m-%Y',
            '%Y-%m-%d',
            '%d/%m/%y',
            '%d-%m-%y',
            '%Y/%m/%d'
        ]
        
        for fmt in date_formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        
        return None
    
    def _parse_amount(self, amount_str: str) -> Optional[float]:
        """Converte string de valor para float"""
        if not amount_str:
            return None
        
        try:
            # Remover caracteres não numéricos exceto vírgula, ponto e sinal de menos
            cleaned = ''.join(c for c in amount_str if c.isdigit() or c in '.,+-')
            
            # Substituir vírgula por ponto (formato brasileiro)
            if ',' in cleaned and '.' in cleaned:
                # Se tem ambos, assumir que vírgula é separador decimal
                cleaned = cleaned.replace('.', '').replace(',', '.')
            elif ',' in cleaned:
                cleaned = cleaned.replace(',', '.')
            
            return float(cleaned)
            
        except (ValueError, TypeError):
            return None
    
    def _parse_transaction_type(self, type_str: str, amount: float) -> TransactionType:
        """Determina o tipo da transação"""
        if not type_str:
            # Se não especificado, usar o sinal do valor
            return TransactionType.INCOME if amount >= 0 else TransactionType.EXPENSE
        
        type_str = type_str.lower().strip()
        
        # Mapeamento de tipos
        income_keywords = ['receita', 'entrada', 'credito', 'crédito', 'income', 'credit', '+']
        expense_keywords = ['despesa', 'saida', 'saída', 'debito', 'débito', 'expense', 'debit', '-']
        
        if any(keyword in type_str for keyword in income_keywords):
            return TransactionType.INCOME
        elif any(keyword in type_str for keyword in expense_keywords):
            return TransactionType.EXPENSE
        else:
            # Se não conseguir determinar, usar o sinal do valor
            return TransactionType.INCOME if amount >= 0 else TransactionType.EXPENSE
    
    def _build_categories_cache(self) -> Dict[str, int]:
        """Constrói cache de categorias existentes"""
        categories = db.session.query(Category).all()
        return {cat.name.lower(): cat.id for cat in categories}
    
    def _build_accounts_cache(self) -> Dict[str, int]:
        """Constrói cache de contas existentes"""
        accounts = db.session.query(Account).all()
        return {acc.name.lower(): acc.id for acc in accounts}
    
    def _get_or_create_category(self, category_name: str, cache: Dict[str, int]) -> int:
        """Obtém ID da categoria ou cria uma nova"""
        if not category_name:
            category_name = 'Outros'
        
        category_key = category_name.lower()
        
        if category_key in cache:
            return cache[category_key]
        
        # Criar nova categoria
        new_category = Category(
            name=category_name,
            description=f'Categoria criada automaticamente durante importação',
            color='#6b7280',  # Cor padrão cinza
            is_default=False
        )
        
        db.session.add(new_category)
        db.session.flush()  # Para obter o ID
        
        cache[category_key] = new_category.id
        return new_category.id
    
    def _get_or_create_account(self, account_name: str, cache: Dict[str, int]) -> int:
        """Obtém ID da conta ou cria uma nova"""
        if not account_name:
            account_name = 'Conta Principal'
        
        account_key = account_name.lower()
        
        if account_key in cache:
            return cache[account_key]
        
        # Criar nova conta
        from src.models.financial import AccountType
        new_account = Account(
            name=account_name,
            account_type=AccountType.CHECKING,
            bank_name='Banco não especificado',
            balance=0.0
        )
        
        db.session.add(new_account)
        db.session.flush()  # Para obter o ID
        
        cache[account_key] = new_account.id
        return new_account.id
    
    def get_import_template(self) -> Dict:
        """Retorna template/exemplo para importação"""
        return {
            'required_columns': self.required_columns,
            'optional_columns': self.optional_columns,
            'supported_formats': self.supported_formats,
            'example_data': [
                {
                    'data': '01/01/2025',
                    'descricao': 'Salário Janeiro',
                    'valor': '5000.00',
                    'tipo': 'receita',
                    'categoria': 'Salário',
                    'conta': 'Conta Corrente',
                    'observacoes': 'Pagamento mensal'
                },
                {
                    'data': '02/01/2025',
                    'descricao': 'Supermercado',
                    'valor': '-250.50',
                    'tipo': 'despesa',
                    'categoria': 'Alimentação',
                    'conta': 'Cartão de Crédito',
                    'observacoes': 'Compras da semana'
                }
            ],
            'column_descriptions': {
                'data': 'Data da transação (DD/MM/AAAA ou DD-MM-AAAA)',
                'descricao': 'Descrição da transação',
                'valor': 'Valor da transação (positivo para receitas, negativo para despesas)',
                'tipo': 'Tipo: receita/entrada/credito ou despesa/saida/debito',
                'categoria': 'Categoria da transação (será criada se não existir)',
                'conta': 'Conta ou cartão (será criada se não existir)',
                'observacoes': 'Observações adicionais (opcional)'
            },
            'note': 'Atualmente suportamos apenas arquivos CSV. Suporte para Excel será adicionado em breve.'
        }

