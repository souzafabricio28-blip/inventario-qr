CREATE TABLE IF NOT EXISTS recebimentos_nf (
    id BIGSERIAL PRIMARY KEY,
    chave_acesso TEXT,
    numero TEXT,
    serie TEXT,
    fornecedor TEXT DEFAULT '',
    cnpj_fornecedor TEXT DEFAULT '',
    data_emissao TEXT DEFAULT '',
    data_recebimento TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'aberto',
    total_itens INTEGER DEFAULT 0,
    itens_recebidos INTEGER DEFAULT 0,
    finalizado_em TIMESTAMP,
    excluido INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS itens_recebimento (
    id BIGSERIAL PRIMARY KEY,
    recebimento_id BIGINT NOT NULL,
    ean TEXT DEFAULT '',
    codigo_produto TEXT DEFAULT '',
    descricao TEXT NOT NULL,
    ncm TEXT DEFAULT '',
    unidade TEXT DEFAULT 'UN',
    quantidade_esperada DOUBLE PRECISION DEFAULT 1,
    quantidade_recebida DOUBLE PRECISION DEFAULT 0,
    lote TEXT DEFAULT '',
    data_vencimento TEXT DEFAULT '',
    CONSTRAINT fk_itens_recebimento
        FOREIGN KEY (recebimento_id) REFERENCES recebimentos_nf(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS produtos (
    id BIGSERIAL PRIMARY KEY,
    ean TEXT UNIQUE NOT NULL,
    produto TEXT NOT NULL,
    marca TEXT NOT NULL DEFAULT '',
    unidade_medida TEXT DEFAULT 'UN',
    base_especifica TEXT DEFAULT '',
    instrucao_dosagem TEXT DEFAULT '',
    lote TEXT DEFAULT '',
    data_vencimento TEXT DEFAULT '',
    codigo_interno TEXT DEFAULT '',
    quantidade_estoque DOUBLE PRECISION DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS produto_codigos (
    codigo TEXT PRIMARY KEY,
    ean_produto TEXT NOT NULL,
    origem TEXT DEFAULT 'bip',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_produto_codigos_ean
        FOREIGN KEY (ean_produto) REFERENCES produtos(ean) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS inventario_contagem (
    id BIGSERIAL PRIMARY KEY,
    ean TEXT NOT NULL,
    quantidade_contada INTEGER DEFAULT 1,
    lote TEXT DEFAULT '',
    data_vencimento TEXT DEFAULT '',
    data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sessao TEXT DEFAULT '',
    loja TEXT DEFAULT 'RTJ',
    CONSTRAINT fk_contagem_ean
        FOREIGN KEY (ean) REFERENCES produtos(ean)
);

CREATE TABLE IF NOT EXISTS sessoes_inventario (
    id BIGSERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    loja TEXT DEFAULT 'RTJ',
    data_abertura TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data_fechamento TIMESTAMP,
    status TEXT DEFAULT 'aberta'
);

CREATE TABLE IF NOT EXISTS validacoes_base (
    id BIGSERIAL PRIMARY KEY,
    ean TEXT NOT NULL,
    base_informada TEXT NOT NULL,
    base_oficial TEXT NOT NULL,
    status TEXT DEFAULT 'pendente',
    data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_validacoes_ean
        FOREIGN KEY (ean) REFERENCES produtos(ean)
);

CREATE TABLE IF NOT EXISTS saidas_estoque (
    id BIGSERIAL PRIMARY KEY,
    ean TEXT NOT NULL DEFAULT '',
    produto TEXT DEFAULT '',
    quantidade DOUBLE PRECISION DEFAULT 1,
    lote TEXT DEFAULT '',
    data_vencimento TEXT DEFAULT '',
    motivo TEXT DEFAULT '',
    observacao TEXT DEFAULT '',
    loja TEXT DEFAULT '',
    data_saida TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS estoque_produto (
    ean TEXT NOT NULL,
    loja TEXT NOT NULL DEFAULT 'RTJ',
    quantidade_estoque DOUBLE PRECISION NOT NULL DEFAULT 0,
    lote TEXT DEFAULT '',
    data_vencimento TEXT DEFAULT '',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ean, loja)
);

CREATE TABLE IF NOT EXISTS config (
    chave TEXT PRIMARY KEY,
    valor TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS usuarios (
    id BIGSERIAL PRIMARY KEY,
    usuario TEXT UNIQUE NOT NULL,
    senha_hash TEXT NOT NULL,
    nome TEXT DEFAULT '',
    ativo INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_inventario_ean ON inventario_contagem(ean);
CREATE INDEX IF NOT EXISTS idx_inventario_sessao ON inventario_contagem(sessao);
CREATE INDEX IF NOT EXISTS idx_produtos_ean ON produtos(ean);
CREATE INDEX IF NOT EXISTS idx_validacoes_ean ON validacoes_base(ean);
CREATE INDEX IF NOT EXISTS idx_usuarios_usuario ON usuarios(usuario);

-- Migração para bancos existentes
ALTER TABLE inventario_contagem ADD COLUMN IF NOT EXISTS loja TEXT DEFAULT 'RTJ';
ALTER TABLE sessoes_inventario ADD COLUMN IF NOT EXISTS loja TEXT DEFAULT 'RTJ';
ALTER TABLE saidas_estoque ADD COLUMN IF NOT EXISTS loja TEXT DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_inventario_loja ON inventario_contagem(loja);
CREATE INDEX IF NOT EXISTS idx_sessoes_loja ON sessoes_inventario(loja);
CREATE INDEX IF NOT EXISTS idx_estoque_produto_loja ON estoque_produto(loja);