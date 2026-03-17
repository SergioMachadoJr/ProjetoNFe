# ProjetoNFe

Implementação base para captura de NF-e de entrada via SEFAZ (NFeDistribuicaoDFe), usando certificado A1 e gravação em diretório de rede.

## Início rápido
```bash
cp config/config.exemplo.yaml config/config.yaml
# ajuste o arquivo config/config.yaml
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python src/captura_nfe_distribuicao.py --config config/config.yaml
```

Documentação completa em `docs/solucao_captura_nfe.md`.
