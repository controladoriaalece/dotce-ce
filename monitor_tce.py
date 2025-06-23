import requests
import smtplib
import os
import re
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import fitz  # PyMuPDF
import unicodedata

# --- CONFIGURAÇÕES DINÂMICAS (LIDAS DAS VARIÁVEIS DE AMBIENTE) ---

# As credenciais e destinatários são lidos de forma segura a partir das "Secrets" do GitHub
SMTP_SERVER = 'smtp.gmail.com'  # Ex: 'smtp.gmail.com' ou 'smtp.office365.com'
SMTP_PORT = 587                   # Porta do servidor SMTP (587 para TLS)
EMAIL_SENDER = os.getenv('EMAIL_SENDER')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
# Os destinatários são lidos como uma string separada por vírgulas e convertidos para uma lista
EMAIL_RECIPIENTS_STR = os.getenv('EMAIL_RECIPIENTS')

# Validação para garantir que as variáveis de ambiente foram configuradas no GitHub
if not all([EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENTS_STR]):
    print("ERRO: Variáveis de ambiente (EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENTS) não foram configuradas nos Secrets do GitHub.")
    exit(1) # Encerra o script se as credenciais não estiverem disponíveis

# Converte a string de e-mails em uma lista de e-mails
EMAIL_RECIPIENTS = [email.strip() for email in EMAIL_RECIPIENTS_STR.split(',')]

# --- CONFIGURAÇÕES GERAIS ---
BASE_URL = "https://contexto-api.tce.ce.gov.br/arquivos/doe?url=%2F{year_code}%2FDOTCECE_{year_code}-{gazette_number}.pdf"
START_GAZETTE_NUMBER = 112
SEARCH_TERMS = ['Secretaria de Educação', 'Secretaria de Juventude', 'Instituto Dr. José Frota']

def normalize_text(text):
    """
    Remove acentos, cedilhas e converte para minúsculas para uma comparação eficaz.
    """
    try:
        nfkd_form = unicodedata.normalize('NFD', text)
        only_ascii = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
        return only_ascii.lower()
    except TypeError:
        return ""

def get_latest_gazette_info():
    """
    Encontra a URL e o nome do arquivo do diário mais recente.
    """
    print("Procurando pelo diário oficial mais recente...")
    try:
        current_year = datetime.now().year
        year_code = current_year - 2013
        gazette_number = START_GAZETTE_NUMBER
        last_successful_url = None
        last_successful_filename = None
        search_limit = gazette_number + 500 

        while gazette_number < search_limit:
            file_name = f"DOTCECE_{year_code}-{gazette_number}.pdf"
            encoded_path = f"%2F{year_code}%2F{file_name}"
            url_to_check = f"https://contexto-api.tce.ce.gov.br/arquivos/doe?url={encoded_path}"
            print(f"Tentando verificar: {file_name}...")
            response = requests.head(url_to_check, allow_redirects=True, timeout=15)

            if response.status_code == 200:
                print(f"Sucesso! Diário encontrado: {file_name}")
                last_successful_url = url_to_check
                last_successful_filename = file_name
                gazette_number += 1
            else:
                print(f"Falha ao encontrar o diário nº {gazette_number} (Status: {response.status_code}).")
                break
    except requests.exceptions.RequestException as e:
        print(f"Erro de conexão ao tentar encontrar o diário: {e}")
        return None, None
        
    return last_successful_url, last_successful_filename

def download_pdf(url, filename):
    """
    Baixa o arquivo PDF da URL fornecida.
    """
    print(f"Baixando o arquivo: {filename}...")
    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        filepath = os.path.join(os.getcwd(), filename)
        with open(filepath, 'wb') as f:
            f.write(response.content)
        print(f"Download completo. Arquivo salvo em: {filepath}")
        return filepath
    except requests.exceptions.RequestException as e:
        print(f"Erro ao baixar o PDF: {e}")
        return None

def analyze_pdf_and_find_terms(pdf_path, search_terms):
    """
    Lê o texto de um PDF, separa em publicações e busca por termos específicos, ignorando acentos e caixa.
    """
    print("Analisando o conteúdo do PDF...")
    matched_publications = []
    full_text = ""
    try:
        with fitz.open(pdf_path) as doc:
            for page in doc:
                full_text += page.get_text("text", sort=True) + "\n\n"
    except Exception as e:
        print(f"Erro ao ler o arquivo PDF: {e}")
        return []

    split_patterns = [
        r'^\s*\*\s?\*\s?\*\s?\*\s?\*\s?\*\s?\*\s*$', r'^PROCESSO:\s*\d{5}/\d{4}-\d$',
        r'^\d+\s+-\s+Processo\s+nº', r'^ACÓRDÃO\s+Nº\s+\d+/\d{4}$',
        r'^ACÓRDÃO\s+N\.º\s+\d+/\d{4}$', r'^COMUNICAÇÃO\s+PROCESSUAL\s+DOE-TCE/CE\s+N°',
        r'^ATO\s+DA\s+PRESIDÊNCIA\s+Nº', r'^OFÍCIO CIRCULAR\s+Nº', r'^ATO\s+Nº', r'^PORTARIA\s+Nº?'
    ]
    combined_pattern = '|'.join(split_patterns)
    lines = full_text.split('\n')
    publications = []
    current_publication = ""

    for line in lines:
        if re.search(combined_pattern, line.strip(), re.IGNORECASE):
            if current_publication.strip():
                publications.append(current_publication)
            current_publication = line + "\n"
        else:
            current_publication += line + "\n"
    if current_publication.strip():
        publications.append(current_publication)

    print(f"Identificadas {len(publications)} publicações para análise.")
    normalized_search_terms = {normalize_text(term): term for term in search_terms}

    for pub_text in publications:
        normalized_pub_text = normalize_text(pub_text)
        terms_found_in_pub = [orig_term for norm_term, orig_term in normalized_search_terms.items() if norm_term in normalized_pub_text]
        if terms_found_in_pub:
            matched_publications.append((pub_text.strip(), terms_found_in_pub))
    return matched_publications

def send_email_with_attachment(subject, body, recipients, attachment_path):
    """
    Envia um e-mail para uma lista de destinatários em cópia oculta (BCC).
    """
    print(f"Preparando e-mail para {len(recipients)} destinatário(s)...")
    msg = MIMEMultipart()
    msg['From'] = f"Robô DOTCE-CE <{EMAIL_SENDER}>"
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    try:
        with open(attachment_path, 'rb') as attachment:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="{os.path.basename(attachment_path)}"');
            msg.attach(part)
    except FileNotFoundError:
        print(f"Erro: Arquivo de anexo não encontrado em {attachment_path}")
        return

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        # O campo 'To' é omitido, e os destinatários são passados no sendmail,
        # tratando-os efetivamente como BCC (Cópia Oculta).
        server.sendmail(EMAIL_SENDER, recipients, msg.as_string())
        server.quit()
        print("E-mail enviado com sucesso!")
    except Exception as e:
        print(f"Falha ao enviar o e-mail: {e}")

def get_footer_message():
    """Retorna a mensagem de rodapé padrão para os e-mails."""
    footer = "\n\n💡 Caso sinta falta de alguma publicação, por gentileza me comunique em resposta a este e-mail para a melhoria contínua da minha atuação. 🦾\n\n"
    footer += "Atenciosamente,\n"
    footer += "🤖 Robô extraoficial de notificações do DOTCE-CE 📄"
    return footer

if __name__ == "__main__":
    url, filename = get_latest_gazette_info()
    
    if url and filename:
        attachment_path = download_pdf(url, filename)
        
        if attachment_path:
            analysis_results = analyze_pdf_and_find_terms(attachment_path, SEARCH_TERMS)
            
            if analysis_results:
                total_pubs_found = len(analysis_results)
                term_counts = {term: 0 for term in SEARCH_TERMS}
                for _, terms_found in analysis_results:
                    for term in terms_found:
                        term_counts[term] += 1

                subject = f"📰🔵✅ {filename} (Termos encontrados) 📢"
                
                body = "🤖 Olá,\n\n"
                body += f"Resumo da Pesquisa no Diário '{filename}':\n"
                body += f"- Total de publicações com termos de interesse: {total_pubs_found}\n"
                for term, count in term_counts.items():
                    if count > 0:
                        body += f"- O termo '{term}' foi encontrado em {count} publicação(ões).\n"

                body += "\nO arquivo PDF completo do DOTCE-CE está em anexo para consulta.\n\n"
                body += "============ 📄 PUBLICAÇÕES ENCONTRADAS 📄 ============\n\n"
                
                for i, (pub_text, terms_found) in enumerate(analysis_results, 1):
                    terms_str = ", ".join(f"'{t}'" for t in terms_found)
                    body += f"-------------------- ⚠️ Publicação nº {i} (Termo(s) encontrado(s): {terms_str}) ⚠️ --------------------\n\n"
                    body += f"{pub_text}\n\n"
            
            else:
                subject = f"📰🔵❌ {filename} (Termos não encontrados)"
                body = f"🤖 Olá,\n\nEsta é uma confirmação de que a verificação no Diário Oficial do Tribunal de Contas do Estado do Ceará mais recente disponível ({filename}) foi realizada com sucesso.\n\n"
                body += f"Nenhuma publicação com os termos pesquisados foi encontrada.\n\n"
                body += "O arquivo PDF do DOTCE-CE está em anexo para consulta."
            
            body += get_footer_message()
            send_email_with_attachment(subject, body, EMAIL_RECIPIENTS, attachment_path)
            
            print(f"Removendo arquivo temporário: {attachment_path}")
            os.remove(attachment_path)
    else:
        print("Não foi possível encontrar um novo Diário Oficial ou ocorreu um erro.")
