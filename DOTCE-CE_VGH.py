# Nome do seu arquivo .py (ex: DOTCE-CE_VGH.py)

import os
import time
import re
import fitz  # PyMuPDF
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

from selenium import webdriver
from selenium.webdriver.common.by import By
# webdriver-manager NÃO é importado
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def encontrar_publicacoes(caminho_pdf, termo_busca):
    """
    Abre um arquivo PDF, extrai seu texto e procura por publicações
    que contenham o termo de busca.
    """
    print(f"Pesquisando o termo '{termo_busca}' no arquivo {caminho_pdf}...")
    publicacoes_encontradas = []
    try:
        doc = fitz.open(caminho_pdf)
        texto_completo = ""
        for pagina in doc:
            texto_completo += pagina.get_text("text", sort=True)
        doc.close()

        padrao_publicacao = re.compile(r'^\s*(PORTARIA|ATO|DECRETO|AVISO|EXTRATO DE|RESOLUÇÃO|INSTRUÇÃO NORMATIVA)', re.MULTILINE | re.IGNORECASE)
        possiveis_publicacoes = padrao_publicacao.split(texto_completo)
        
        publicacoes = []
        for i in range(1, len(possiveis_publicacoes), 2):
            publicacoes.append(possiveis_publicacoes[i] + possiveis_publicacoes[i+1])

        for pub in publicacoes:
            if re.search(termo_busca, pub, re.IGNORECASE):
                print("Termo encontrado em uma publicação.")
                publicacoes_encontradas.append(pub.strip())
        
        return publicacoes_encontradas
    except Exception as e:
        print(f"Erro ao ler e pesquisar o PDF: {e}")
        return []

def enviar_email(assunto, corpo_html, destinatario, caminho_anexo):
    """
    Envia um e-mail com o PDF em anexo.
    """
    remetente = os.environ.get('EMAIL_ADDRESS')
    senha = os.environ.get('EMAIL_PASSWORD')
    servidor_smtp = os.environ.get('SMTP_SERVER')
    porta_smtp = int(os.environ.get('SMTP_PORT', 587))

    if not all([remetente, senha, servidor_smtp, porta_smtp]):
        raise ValueError("ERRO: As variáveis de ambiente para envio de e-mail não foram configuradas.")

    print(f"Preparando e-mail para {destinatario}...")
    msg = MIMEMultipart()
    msg['Subject'] = assunto
    msg['From'] = remetente
    msg['To'] = destinatario
    msg.attach(MIMEText(corpo_html, 'html'))

    with open(caminho_anexo, 'rb') as f:
        anexo = MIMEApplication(f.read(), _subtype='pdf')
        anexo.add_header('Content-Disposition', 'attachment', filename=os.path.basename(caminho_anexo))
        msg.attach(anexo)

    try:
        with smtplib.SMTP(servidor_smtp, porta_smtp) as server:
            server.starttls()
            server.login(remetente, senha)
            server.send_message(msg)
        print("E-mail enviado com sucesso!")
    except Exception as e:
        print(f"Falha ao enviar e-mail: {e}")

def baixar_e_processar_diario():
    pasta_de_download = os.getcwd()
    arquivo_baixado = None
    driver = None
    
    try:
        print("Configurando o Firefox em modo headless...")
        options = webdriver.FirefoxOptions()
        options.add_argument("--headless")
        options.set_preference("browser.download.folderList", 2)
        options.set_preference("browser.download.dir", pasta_de_download)
        options.set_preference("browser.helperApps.neverAsk.saveToDisk", "application/pdf")
        options.set_preference("pdfjs.disabled", True)

        # --- LINHA CORRIGIDA ---
        # Diz ao Selenium para usar o driver que a Action do GitHub já instalou.
        service = FirefoxService()
        
        driver = webdriver.Firefox(service=service, options=options)
        
        pagina_url = "https://www.tce.ce.gov.br/diario-oficial/consulta-por-data-de-edicao"
        print(f"Acessando: {pagina_url}")
        driver.get(pagina_url)

        wait = WebDriverWait(driver, 40)
        print("Aguardando e mudando o foco para o iframe...")
        iframe = wait.until(EC.presence_of_element_located((By.TAG_NAME, "iframe")))
        driver.switch_to.frame(iframe)
        
        print("Selecionando a opção 'Última Edição'...")
        radio_ultima_edicao = wait.until(EC.element_to_be_clickable((By.XPATH, "//label[contains(text(), 'Última Edição')]/preceding-sibling::div//input[@type='radio']")))
        radio_ultima_edicao.click()
        time.sleep(1)

        print("Aguardando o botão 'Visualizar Edição'...")
        botao_visualizar = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@value='Visualizar Edição']")))
        botao_visualizar.click()

        print("Download iniciado. Aguardando conclusão...")
        tempo_limite = 90
        tempo_inicial = time.time()
        while time.time() - tempo_inicial < tempo_limite:
            arquivos_na_pasta = os.listdir(pasta_de_download)
            arquivos_pdf = [f for f in arquivos_na_pasta if f.lower().endswith('.pdf') and not f.lower().endswith('.part')]
            if arquivos_pdf:
                arquivo_baixado = os.path.join(pasta_de_download, arquivos_pdf[0])
                if time.time() - os.path.getmtime(arquivo_baixado) < 20:
                    print(f"Download concluído: {arquivo_baixado}")
                    break
            time.sleep(2)
        else:
             raise Exception("Timeout: O download do arquivo PDF demorou demais.")
    
    finally:
        if driver:
            driver.quit()
            print("Navegador Firefox automatizado foi fechado.")

    if arquivo_baixado:
        termo = "Assembleia Legislativa do Estado do Ceará"
        publicacoes = encontrar_publicacoes(arquivo_baixado, termo)

        if publicacoes:
            print(f"Total de {len(publicacoes)} publicações encontradas com o termo.")
            destinatario_email = os.environ.get('RECIPIENT_EMAIL')
            
            corpo = f"<h3>Foram encontradas {len(publicacoes)} publicações contendo o termo '{termo}' no Diário Oficial.</h3>"
            corpo += "<p>O arquivo PDF completo segue em anexo.</p><hr>"
            for i, pub in enumerate(publicacoes, 1):
                corpo += f"<h4>Publicação {i}:</h4><pre style='white-space: pre-wrap; background-color: #f4f4f4; border: 1px solid #ddd; padding: 10px;'>{pub}</pre><hr>"
            
            data_hoje = time.strftime('%d/%m/%Y')
            assunto_email = f"Alerta de Publicações no Diário do TCE-CE - {data_hoje}"

            enviar_email(assunto_email, corpo, destinatario_email, arquivo_baixado)
        else:
            print("Nenhuma publicação encontrada com o termo de busca. Nenhuma ação necessária.")
    else:
        print("Nenhum arquivo foi baixado, script encerrado.")

if __name__ == "__main__":
    baixar_e_processar_diario()
