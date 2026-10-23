"""Texto de orientação. Nenhum passo daqui é executado pelo aplicativo."""

INSTRUCTIONS = """\
Este monitor apenas consulta e informa.

Ele não atualiza o Iceman, não substitui o ProxSpace, não instala pacotes,
não compila por causa de uma release nova e não grava firmware nem bootrom.

Uma release ou um commit mais novo não significa que a imagem atual continue
compatível. Mudanças podem afetar o Makefile, os módulos Standalone, a
toolchain, o bootloader, a plataforma, a flash SPI e o cliente Proxmark3.
Enquanto isso não for conferido, a compatibilidade permanece não verificada.

O repositório oficial do ProxSpace pode aparecer como arquivado. Isso não
torna a instalação local inutilizável nem prova que ela esteja desatualizada.

A versão gravada no Proxmark3 físico é outra informação. Ela não é a versão
do código-fonte selecionado neste computador.

Não há, nesta versão, um comando para aplicar a atualização. Qualquer
atualização futura precisa de backup, de um checkout separado e de uma
autorização explícita. Este painel não faz isso.
"""
