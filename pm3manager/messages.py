"""Frases mostradas ao usuário. Os códigos correspondentes ficam nos resultados."""


class Msg:
    NOT_FOUND = "Proxmark3 não encontrado."
    MODEL_UNCONFIRMED = "Não foi possível confirmar o modelo conectado."
    INCOMPATIBLE_MODULE = "Módulo incompatível com PM3GENERIC nesta instalação."
    COMPILE_OK = "Compilação concluída."
    COMPILE_FAIL = "Falha ao compilar firmware."
    PREPARE_FLASH = "Preparando gravação."
    WAIT_RECONNECT = "Aguardando reconexão do dispositivo."
    # OK200 só cabe depois de prova em laboratório. O fluxo automático não emite este texto.
    FLASH_VALIDATED = "Firmware gravado e comunicação validada."
    FLASH_PARTIAL = "Firmware gravado, porém validação incompleta."
    FLASH_UNCONFIRMED = (
        "Não foi possível confirmar a gravação. "
        "O comando não terminou com sucesso. Uma reconexão posterior não comprova o flashing."
    )
    FLASH_NO_RECONNECT = (
        "O comando de gravação informou 'All done', mas o dispositivo não reconectou. "
        "Comunicação, versão, plataforma e módulo Standalone não foram confirmados."
    )
    FLASH_NO_COMM = (
        "O dispositivo reconectou, mas a comunicação com o firmware não foi confirmada. "
        "Versão, plataforma e módulo Standalone continuam pendentes."
    )
    FLASH_VERSION_MISMATCH = (
        "O dispositivo respondeu, mas a versão do firmware não confere com o repositório. "
        "O módulo Standalone não foi confirmado."
    )
    FLASH_PARTIAL_CHECK = (
        "Validação parcial. A gravação informou 'All done', o dispositivo reconectou, "
        "a comunicação foi restabelecida e a versão confere. "
        "O módulo Standalone não foi confirmado: hw version e hw status desta versão do Iceman "
        "não identificam de forma inequívoca o módulo ativo. "
        "A seleção na interface não confirma o módulo, e o funcionamento com hardware de laboratório não foi testado."
    )
    COMM_ERROR = "Erro de comunicação."
    DEVICE_INCOMPATIBLE = "Dispositivo incompatível."
    PROXSPACE_MISSING = (
        "ProxSpace não encontrado. Selecione a pasta da instalação. "
        "Ela precisa conter runme64.bat e msys2\\msys2_shell.cmd."
    )
    # OK202: o diagnóstico comunicou, mas a imagem deste aplicativo é PM3GENERIC.
    RDV4_DIAGNOSTIC = (
        "Comunicação estabelecida. O firmware identificado é RDV4. "
        "A leitura e o diagnóstico continuam disponíveis, mas a gravação de uma imagem PM3GENERIC está bloqueada."
    )
    FLASH_RDV4_BLOCKED = (
        "Gravação bloqueada. O dispositivo foi identificado como RDV4 e esta imagem é PM3GENERIC."
    )
    RDV4_PIPELINE_BLOCKED = (
        "Compilação e gravação bloqueadas. O dispositivo foi identificado como RDV4 e esta imagem é PM3GENERIC. "
        "A leitura continua disponível; este aplicativo não compila nem grava para RDV4."
    )
    FLASH_PM5_BLOCKED = (
        "Compilação e gravação bloqueadas. O dispositivo foi identificado como Proxmark5. "
        "Este aplicativo não envia firmware PM3 para esse aparelho e não tem pipeline PM5."
    )
    FLASH_IDENTITY_BLOCKED = (
        "Compilação e gravação bloqueadas. A identificação do firmware é inconclusiva ou conflitante, "
        "então a imagem PM3GENERIC não será aplicada."
    )
    IDENTIFYING = (
        "A identificação do dispositivo está em andamento. Compilação e gravação esperam ela terminar."
    )
    FLASH_SIZE_BLOCKED = (
        "Gravação bloqueada. O tamanho da flash interna não confere com PLATFORM_SIZE da imagem."
    )
    BUSY = "Já existe uma compilação ou gravação em andamento."
    FLASH_NOT_AUTHORIZED = (
        "Compilação concluída. A gravação real não foi executada porque ainda não há autorização."
    )
    REQUIREMENTS = (
        "Compatibilidade incerta nesta versão do firmware. "
        "A compilação automática está bloqueada até você confirmar os requisitos."
    )
    FLASH_REQUIRED = (
        "Este módulo exige memória flash SPI externa. Confirme o hardware antes de compilar."
    )

    @staticmethod
    def detected(port: str) -> str:
        return f"Dispositivo detectado na {port}."
