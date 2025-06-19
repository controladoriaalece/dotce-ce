# baixar_diario.py
import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.firefox import GeckoDriverManager

def baixar_diario_para_github():
    """
    Versão adaptada para rodar em um servidor (GitHub Actions),
    salvando o arquivo na pasta do projeto.
    """
    # A pasta de download será a mesma pasta onde o script está.
    pasta_de_download = os.getcwd()
    print(f"O arquivo será salvo em: {pasta_de_download}")
    
    driver = None
    try:
        # --- Configuração do Firefox para rodar em servidor ---
        print("Configurando o Firefox em modo headless...")
        options = webdriver.FirefoxOptions()
        # O modo headless é OBRIGATÓRIO em ambientes de servidor
        options.add_argument("--headless")
        
        # Configurações para o download automático
        options.set_preference("browser.download.folderList", 2)
        options.set_preference("browser.download.dir", pasta_de_download)
        options.set_preference("browser.download.useDownloadDir", True)
        options.set_preference("browser.helperApps.neverAsk.saveToDisk", "application/pdf")
        options.set_preference("pdfjs.disabled", True)

        # Instala e gerencia o geckodriver
        service = FirefoxService(GeckoDriverManager().install())
        driver = webdriver.Firefox(service=service, options=options)
        
        # --- Lógica de Navegação ---
        pagina_url = "https://www.tce.ce.gov.br/diario-oficial/consulta-por-data-de-edicao"
        print(f"Acessando: {pagina_url}")
        driver.get(pagina_url)

        wait = WebDriverWait(driver, 30) # Aumentado o tempo de espera para ambientes de servidor
        
        print("Aguardando e mudando o foco para o iframe...")
        iframe = wait.until(EC.presence_of_element_located((By.TAG_NAME, "iframe")))
        driver.switch_to.frame(iframe)
        
        # Clica no rádio "Última Edição" para garantir o estado correto
        print("Selecionando a opção 'Última Edição'...")
        radio_ultima_edicao = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//label[contains(text(), 'Última Edição')]/preceding-sibling::div//input[@type='radio']"))
        )
        radio_ultima_edicao.click()
        time.sleep(1) # Pausa para o JS da página processar

        print("Aguardando o botão 'Visualizar Edição'...")
        botao_visualizar = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//input[@value='Visualizar Edição']"))
        )

        print("Clicando no botão para iniciar o download...")
        botao_visualizar.click()

        # --- Lógica inteligente para aguardar o download ---
        print("Aguardando o download ser concluído...")
        tempo_limite = 90
        tempo_inicial = time.time()
        download_concluido = False
        while time.time() - tempo_inicial < tempo_limite:
            arquivos = os.listdir(pasta_de_download)
            if any(f.lower().endswith('.pdf') and not f.lower().endswith('.part') for f in arquivos):
                print("\nArquivo PDF detectado na pasta!")
                download_concluido = True
                break
            time.sleep(2)

        if not download_concluido:
            print("\nAVISO: O tempo de espera para o download esgotou.")
            # Gerar um erro para que a Action falhe e você seja notificado
            raise Exception("Download timeout")

    finally:
        if driver:
            driver.quit()
            print("Navegador Firefox automatizado foi fechado.")

if __name__ == "__main__":
    baixar_diario_para_github()