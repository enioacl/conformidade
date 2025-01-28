import pandas as pd
import numpy as np
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import time
import base64
import requests
import os

# Lê a planiha Conformidade Legal 
#(https://docs.google.com/spreadsheets/d/1_teMusgzqisvbbL3TOONcjJSBibTTae5AIKp-oeceQg/edit?gid=0#gid=0)

# Em resumo, esse trecho do código, lê todas as abas da planilha do google sheets Conformidade Legal
# e monta um dataframe único com todos os dados.
# Esse processo é interessante de ser realizado via Phyton devido a muitas vezes quando da utilização 
# da solução nativa do Power BI (conector do google sheets) termos experimentados erros com relação 
# à quantidade de requisições (Erro: Too many requests).

# Caminho para o arquivo de credenciais
#SERVICE_ACCOUNT_FILE = "C:\\Arquivos\\Documents\\GOOGLESHEETS_TOKEN.json"
SERVICE_ACCOUNT_FILE = os.environ["google_sheets_id"]
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
SHEET_ID = "1_teMusgzqisvbbL3TOONcjJSBibTTae5AIKp-oeceQg"

# Autenticação com a API do Google Sheets
credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
service = build('sheets', 'v4', credentials=credentials)
sheet = service.spreadsheets()

# Obter todas as abas da planilha
spreadsheet = sheet.get(spreadsheetId=SHEET_ID).execute()
sheet_names = [sheet['properties']['title'] for sheet in spreadsheet['sheets']]

# DataFrame vazio para armazenar todos os links
dados = pd.DataFrame()

# Iterar por cada aba e extrair os dados, ignorando a aba "Dados"
for sheet_name in sheet_names:
    if sheet_name == "Dados":
        continue  # Ignora a aba "Dados"
    
    RANGE = f"{sheet_name}!A1:R1000"  # Ajuste o intervalo conforme necessário
    result = sheet.values().get(spreadsheetId=SHEET_ID, range=RANGE, valueRenderOption='FORMATTED_VALUE').execute()
    values = result.get('values', [])

    if values:
        # Verificar se o número de colunas no cabeçalho é igual ao número de colunas nos dados
        num_columns = len(values[0])
        for row in values[1:]:
            while len(row) < num_columns:
                row.append("")  # Preencher colunas vazias com string vazia
            while len(row) > num_columns:
                row.pop()  # Remover colunas extras

        # Criar DataFrame a partir da aba atual
        dados_aux = pd.DataFrame(values[1:], columns=values[0])  # Primeira linha como cabeçalho
        dados=pd.concat([dados,dados_aux],ignore_index=True)
        # Verificar os nomes das colunas
        #print(f"Colunas da aba '{sheet_name}': {df.columns.tolist()}")

dados["IAD"]= dados["ESTADO DE CUMPRIMENTO"].apply(
                lambda x:"" if x in ["Em Análise","Em análise","Não se aplica"] else x)
dados['NORMA - ORIGEM']=dados['NORMA']+" - "+dados['ORIGEM']                
        

# A partir desse ponto inicia-se a geração da tabela de links. A partir dela é que vamos identificar
# quais são as normas que já têm o questionário respondido a fim de que se possa incluir as informações
# no BI Conformidade.

links=dados[["NORMA","ORIGEM","LINK PARA PLANILHA","ÁREA RESPONSÁVEL","ESTADO DE CUMPRIMENTO"]]
# Remover espaços extras das células da coluna 'LINK PARA FORMULÁRIO'
links['LINK PARA PLANILHA'] = links['LINK PARA PLANILHA'].str.strip()
links['NORMA - ORIGEM']=links['NORMA']+" - "+links['ORIGEM']

# Filtrar o DataFrame para manter apenas as linhas com link informado (não vazio ou nulo)
links_filtrados = links[links['LINK PARA PLANILHA'].str.startswith('https://', na=False)]
links_filtrados = links_filtrados[(links_filtrados['ESTADO DE CUMPRIMENTO'] != "Em análise") & 
                                  (links_filtrados['ESTADO DE CUMPRIMENTO'] != "Não se aplica")]


# Nesse trecho, geramos uma base única com todas as informações provenientes de todas as planilhas
# dos questionários respondidos. O resultado é salvo na variável "base_transposta".

# Extrair IDs das planilhas
links_filtrados['LINK PLANILHA'] = links_filtrados['LINK PARA PLANILHA'].str.extract(r'/d/([^/]+)/')
SHEET_IDS_ITENS = links_filtrados['LINK PLANILHA'].dropna().tolist()

# Inicializar lista para armazenar os DataFrames temporários
dataframes = []
base_transposta=pd.DataFrame()
# Processar cada planilha
for index, sheet_id_item in enumerate(SHEET_IDS_ITENS):
    try: 
        # Obter valores da planilha
        RANGE_ITEM = "A1:ZZZ2"
        resultado = sheet.values().get(spreadsheetId=sheet_id_item, range=RANGE_ITEM, valueRenderOption='FORMATTED_VALUE').execute()
        valores = resultado.get('values', [])
        
        if valores:
            # Ajustar inconsistências no número de colunas
            num_columns = len(valores[0])
            valores = [row + [""] * (num_columns - len(row)) for row in valores]
            
            # Criar DataFrame com os dados da planilha
            base_aux = pd.DataFrame(valores[1:], columns=valores[0])
            
            # Adicionar a linha 'norma' ao final do DataFrame temporário
            norma_row = [links_filtrados.iloc[index]['NORMA - ORIGEM']] * len(valores[0])  # Preencher a linha com a norma
            origem_row = [links_filtrados.iloc[index]['ORIGEM']] * len(valores[0])  # Preencher a linha com a origem
            area_row= [links_filtrados.iloc[index]['ÁREA RESPONSÁVEL']] * len(valores[0])  # Preencher a linha com a área responsável
            base_aux.loc[len(base_aux)] = norma_row  # Adiciona a linha ao final do DataFrame
            base_aux.loc[len(base_aux)] = origem_row  # Adiciona a linha ao final do DataFrame
            base_aux.loc[len(base_aux)] = area_row  # Adiciona a linha ao final do DataFrame
            
            # Adicionar o DataFrame à lista
            base_transposta_aux = base_aux.transpose()
            base_transposta=pd.concat([base_transposta,base_transposta_aux],ignore_index=False)
        time.sleep(5)
    
    except Exception as e:
        print(f"Erro ao processar a planilha {sheet_id_item}: {e}")

base_transposta = base_transposta.drop(['Carimbo de data/hora','Comentário / Evidências',
                                       'Comentário/Evidência'], axis=0)
# Criar uma máscara para identificar as linhas que contêm as expressões
masc=~base_transposta.index.str.contains(r"evidência do cumprimento",case=False,na=False)
base_transposta=base_transposta[masc]

# Criando as tabelas dimensão

origem = pd.DataFrame(dados['ORIGEM'].unique())
tema = pd.DataFrame(dados['TEMA'].unique())
tipo_norma = pd.DataFrame(["Resolução"])
area= pd.DataFrame(dados['ÁREA RESPONSÁVEL'].unique())
estado_analise= pd.DataFrame(['Analisado','Em Análise','Não se Aplica'])
ano= pd.DataFrame(dados['DATA DE REGISTRO'].str.extract(r'(\d{4}$)',expand=False).unique())
situacao= pd.DataFrame(dados['SITUAÇÃO'].unique())
norma=pd.DataFrame(dados['NORMA - ORIGEM'].unique())




#!pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org google-auth
#!pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org google-api-python-client

# Fazendo upload para o GitHub dos arquivos resultantes da execução do código acima
# Configurações gerais
repo_owner = "enioacl"  # Nome do usuário ou organização
repo_name = "conformidade"  # Nome do repositório
branch = "main"
base_api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/"
#token = os.getenv('GITHUB_TOKEN')
token = os.environ["github_id"]
if token is None:
    print("Token do GitHub não encontrado!")
else:
    print("Token carregado com sucesso!")

# Arquivos e conteúdos a serem atualizados

arquivos = [
    {
        "file_path": "Dados.csv",  # Caminho do arquivo no repositório
        "content": dados.to_csv(index=False),  # Convertendo DataFrame para CSV
        "commit_message": "Atualizando Dados.csv"
    },
    {
        "file_path": "base.csv",  # Caminho do segundo arquivo no repositório
        "content": base_transposta.to_csv(index=True),  # Convertendo DataFrame para CSV
        "commit_message": "Atualizando base de itens.csv"
    },
    {
        "file_path": "tab_dimensao/dAno.csv",  # Caminho do segundo arquivo no repositório
        "content": ano.to_csv(index=False),  # Convertendo DataFrame para CSV
        "commit_message": "Atualizando a tabela dimensão dAno"
    },
    {
        "file_path": "tab_dimensao/dArea.csv",  # Caminho do segundo arquivo no repositório
        "content": area.to_csv(index=False),  # Convertendo DataFrame para CSV
        "commit_message": "Atualizando a tabela dimensão dArea"
    },
    {
        "file_path": "tab_dimensao/dEstado_de_Analise.csv",  # Caminho do segundo arquivo no repositório
        "content": estado_analise.to_csv(index=False),  # Convertendo DataFrame para CSV
        "commit_message": "Atualizando a tabela dimensão dEstado_de_analise"
    },
    {
        "file_path": "tab_dimensao/dNorma.csv",  # Caminho do segundo arquivo no repositório
        "content": norma.to_csv(index=False),  # Convertendo DataFrame para CSV
        "commit_message": "Atualizando a tabela dimensão dNorma"
    },
    {
        "file_path": "tab_dimensao/dOrigem.csv",  # Caminho do segundo arquivo no repositório
        "content": origem.to_csv(index=False),  # Convertendo DataFrame para CSV
        "commit_message": "Atualizando a tabela dimensão dOrigem"
    },
    {
        "file_path": "tab_dimensao/dSituacao.csv",  # Caminho do segundo arquivo no repositório
        "content": situacao.to_csv(index=False),  # Convertendo DataFrame para CSV
        "commit_message": "Atualizando a tabela dimensão dSituacao"
    },
    {
        "file_path": "tab_dimensao/dTema.csv",  # Caminho do segundo arquivo no repositório
        "content": tema.to_csv(index=False),  # Convertendo DataFrame para CSV
        "commit_message": "Atualizando a tabela dimensão dTema"
    },
    {
        "file_path": "tab_dimensao/dTipo_de_Norma.csv",  # Caminho do segundo arquivo no repositório
        "content": tipo_norma.to_csv(index=False),  # Convertendo DataFrame para CSV
        "commit_message": "Atualizando a tabela dimensão dTipo_de_Norma"
    }
]

# Função para atualizar um arquivo
def atualizar_arquivo(file_path, content, commit_message):
    api_url = f"{base_api_url}{file_path}"
    encoded_content = base64.b64encode(content.encode()).decode()

    # Obter SHA do arquivo existente
    print(f"Buscando informações do arquivo: {file_path}")
    response = requests.get(api_url, headers={"Authorization": f"token {token}"},verify=False)
    if response.status_code == 200:
        file_info = response.json()
        sha = file_info.get('sha')
        existing_content = base64.b64decode(file_info.get('content', '')).decode()
        if content == existing_content:
            print(f"O conteúdo de {file_path} é idêntico ao atual. Nenhuma atualização será feita.")
            return
    elif response.status_code == 404:
        print(f"Arquivo {file_path} não encontrado no repositório. Ele será criado.")
        sha = None
    else:
        print(f"Erro ao buscar o arquivo {file_path}: {response.status_code} - {response.json()}")
        return

    # Dados do commit
    data = {
        "message": commit_message,
        "content": encoded_content,
        "branch": branch
    }
    if sha:
        data["sha"] = sha

    # Fazer a requisição para criar/atualizar o arquivo
    print(f"Realizando commit/push para {file_path}...")
    commit_response = requests.put(api_url, json=data, headers={"Authorization": f"token {token}"},verify=False)
    if commit_response.status_code in [200, 201]:
        print(f"Commit/push realizado com sucesso para {file_path}!")
    else:
        print(f"Erro ao realizar o commit/push para {file_path}: {commit_response.status_code}")
        print(commit_response.json())

# Atualizar todos os arquivos na lista
for arquivo in arquivos:
    atualizar_arquivo(arquivo["file_path"], arquivo["content"], arquivo["commit_message"])
