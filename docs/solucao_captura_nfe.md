# Solução on-premises para captura de NF-e de entrada (CNPJ destinatário)

## Objetivo
Implementar um processo interno para baixar automaticamente DF-e (principalmente XML de NF-e de entrada) emitidas contra os CNPJs da empresa, utilizando certificado digital A1.

## O que está implementado neste repositório
- Script Python que consulta o serviço **NFeDistribuicaoDFe** da SEFAZ nacional com certificado A1 (.pfx).
- Controle de continuidade por **NSU** (evita baixar repetido e mantém histórico de onde parou).
- Persistência dos XMLs em diretório local/rede, organizado por `CNPJ/AAAA-MM`.
- Arquivo de configuração YAML para múltiplos CNPJs.
- Script de execução para facilitar implantação local.

## Arquivos principais
- `src/captura_nfe_distribuicao.py`: rotina principal de captura.
- `config/config.exemplo.yaml`: parâmetros de ambiente, certificado, destino e CNPJs.
- `scripts/run_capture.sh`: bootstrap e execução.

## Fluxo técnico
1. Lê configuração (ambiente, certificado A1, CNPJs e diretório de saída).
2. Carrega arquivo de estado `nsu-state.json` por CNPJ.
3. Para cada CNPJ, chama NFeDistribuicaoDFe via SOAP com TLS mútua (A1).
4. Lê retorno `docZip`, descompacta e grava XML.
5. Atualiza NSU no arquivo de estado.

## Requisitos de infraestrutura interna
- Servidor Linux/Windows interno com acesso HTTPS à SEFAZ.
- Certificado A1 válido (arquivo `.pfx` + senha).
- Pasta de rede (SMB/NFS) com permissão de escrita para o serviço.
- Agendamento recorrente (cron/systemd timer ou Agendador do Windows).

## Como implantar (Linux)
1. Copie o projeto para o servidor interno.
2. Ajuste `config/config.exemplo.yaml`:
   - `certificado.arquivo_pfx`
   - `certificado.senha`
   - `armazenamento.diretorio_base` (pasta na rede)
   - `armazenamento.estado_nsu_arquivo`
   - lista `cnpjs`
3. Execute manualmente um teste:
   ```bash
   ./scripts/run_capture.sh
   ```
4. Configure agendamento (exemplo: a cada 5 minutos):
   ```cron
   */5 * * * * /workspace/ProjetoNFe/scripts/run_capture.sh >> /var/log/captura-nfe.log 2>&1
   ```

## Boas práticas recomendadas para produção
- Guardar senha do PFX em cofre de segredos (não em texto plano).
- Rodar como usuário de serviço sem privilégio administrativo.
- Criar monitoramento para:
  - falhas de autenticação do certificado,
  - indisponibilidade SEFAZ,
  - crescimento de fila (novos XMLs não processados).
- Versionar e fazer backup do arquivo de estado NSU.
- Aplicar retenção e trilha de auditoria dos arquivos baixados.

## Observações fiscais
- O download via distribuição depende da disponibilidade dos documentos no ambiente nacional.
- Para manifestação do destinatário e eventos adicionais, a empresa pode evoluir com rotinas complementares (ciência/confirmação/operação não realizada).
