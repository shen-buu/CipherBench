"""
SOTA baseline models for algorithm-level fragmented payload identification.

Models:
    - ByteTransformer: Byte-level Transformer with learned positional encoding
    - BiLSTMAttention: Bidirectional LSTM with self-attention pooling
"""

import math
import torch
import torch.nn as nn
import torch.nn.functional as F


# ═══════════════════════════════════════════════════════════
# Byte Transformer
# ═══════════════════════════════════════════════════════════

class LearnedPositionalEncoding(nn.Module):
    """Learned positional encoding for byte sequences."""

    def __init__(self, max_len: int = 1024, d_model: int = 128):
        super().__init__()
        self.pe = nn.Parameter(torch.randn(1, max_len, d_model) * 0.02)

    def forward(self, x):
        # x: [B, L, D]
        return x + self.pe[:, :x.size(1), :]


class ByteTransformer(nn.Module):
    """Byte-level Transformer for payload classification.

    Architecture:
        - Byte embedding (0-255) → d_model
        - Learned positional encoding
        - N stacked TransformerEncoder layers
        - Mean pooling over sequence
        - MLP classifier head

    实际参数量约 1.03M（num_classes=50 时）。
    """

    def __init__(self,
                 num_classes: int = 50,
                 d_model: int = 128,
                 nhead: int = 8,
                 num_layers: int = 4,
                 dim_feedforward: int = 512,
                 dropout: float = 0.1,
                 max_len: int = 1024):
        super().__init__()

        self.d_model = d_model
        self.max_len = max_len

        # Byte embedding: 256 possible byte values → d_model
        self.byte_embed = nn.Embedding(256, d_model, padding_idx=0)

        # Learnable positional encoding
        self.pos_enc = LearnedPositionalEncoding(max_len, d_model)

        # Pre-norm transformer encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            activation='gelu',
            batch_first=True,
            norm_first=True,  # Pre-LN for training stability
        )
        self.encoder = nn.TransformerEncoder(
            encoder_layer,
            num_layers=num_layers,
        )

        # Classifier head
        self.classifier = nn.Sequential(
            nn.Linear(d_model, 256),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(256, 128),
            nn.GELU(),
            nn.Dropout(dropout * 0.5),
            nn.Linear(128, num_classes),
        )

        self._init_weights()

    def _init_weights(self):
        for p in self.parameters():
            if p.dim() > 1:
                nn.init.xavier_uniform_(p)

    def forward(self, x):
        # x: [B, 1, 1024] → [B, 1024]
        if x.dim() == 3:
            x = x.squeeze(1)

        # Convert float [0,1] bytes to integer [0,255]
        byte_ids = (x * 255.0).long().clamp(0, 255)

        # Embed: [B, L] → [B, L, d_model]
        emb = self.byte_embed(byte_ids) * math.sqrt(self.d_model)

        # Add positional encoding
        emb = self.pos_enc(emb)

        # Transformer encoding
        encoded = self.encoder(emb)  # [B, L, d_model]

        # Mean pooling over sequence dimension
        pooled = encoded.mean(dim=1)  # [B, d_model]

        # Classify
        return self.classifier(pooled)


# ═══════════════════════════════════════════════════════════
# BiLSTM with Self-Attention
# ═══════════════════════════════════════════════════════════

class BiLSTMAttention(nn.Module):
    """Bidirectional LSTM with self-attention pooling for byte-level classification.

    Architecture:
        - Conv1D projection (1 → d_model)
        - 2-layer BiLSTM
        - Self-attention pooling over timesteps
        - MLP classifier head

    实际参数量约 0.80M（num_classes=50 时）。
    """

    def __init__(self,
                 num_classes: int = 50,
                 d_model: int = 128,
                 lstm_hidden: int = 128,
                 lstm_layers: int = 2,
                 dropout: float = 0.3,
                 attn_dim: int = 64):
        super().__init__()

        self.d_model = d_model
        self.lstm_hidden = lstm_hidden

        # Input projection: raw bytes → d_model via Conv1D
        self.input_proj = nn.Sequential(
            nn.Conv1d(1, d_model, kernel_size=7, stride=2, padding=3, bias=False),
            nn.BatchNorm1d(d_model),
            nn.GELU(),
        )

        # Bidirectional LSTM
        self.lstm = nn.LSTM(
            input_size=d_model,
            hidden_size=lstm_hidden,
            num_layers=lstm_layers,
            batch_first=True,
            bidirectional=True,
            dropout=dropout if lstm_layers > 1 else 0.0,
        )

        # Self-attention pooling
        bi_hidden = lstm_hidden * 2  # bidirectional
        self.attn_query = nn.Linear(bi_hidden, attn_dim, bias=False)
        self.attn_key = nn.Linear(bi_hidden, attn_dim, bias=False)
        self.attn_scale = math.sqrt(attn_dim)

        # Classifier head
        self.classifier = nn.Sequential(
            nn.Linear(bi_hidden, 256),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(256, 128),
            nn.GELU(),
            nn.Dropout(dropout * 0.5),
            nn.Linear(128, num_classes),
        )

        self._init_weights()

    def _init_weights(self):
        for name, p in self.named_parameters():
            if 'lstm' in name and 'weight' in name:
                if p.dim() > 1:
                    nn.init.orthogonal_(p)
            elif 'weight' in name and p.dim() > 1:
                nn.init.xavier_uniform_(p)

    def forward(self, x):
        # x: [B, 1, 1024]
        # Conv1D projection: [B, 1, 1024] → [B, d_model, L']
        proj = self.input_proj(x)  # e.g. [B, 128, 512]

        # Transpose for LSTM: [B, L', d_model]
        proj = proj.transpose(1, 2)

        # BiLSTM
        lstm_out, _ = self.lstm(proj)  # [B, L', bi_hidden]

        # Self-attention pooling
        Q = self.attn_query(lstm_out)  # [B, L', attn_dim]
        K = self.attn_key(lstm_out)    # [B, L', attn_dim]
        scores = torch.bmm(Q, K.transpose(1, 2)) / self.attn_scale  # [B, L', L']
        attn_weights = scores.mean(dim=1).softmax(dim=-1)  # [B, L'] — aggregate queries
        pooled = torch.bmm(attn_weights.unsqueeze(1), lstm_out).squeeze(1)  # [B, bi_hidden]

        # Classify
        return self.classifier(pooled)


# ═══════════════════════════════════════════════════════════
# Utility
# ═══════════════════════════════════════════════════════════

def count_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


if __name__ == "__main__":
    # Quick tests
    for name, model_cls in [
        ("ByteTransformer", ByteTransformer),
        ("BiLSTMAttention", BiLSTMAttention),
    ]:
        model = model_cls(num_classes=50)
        print(f"\n{'='*50}")
        print(f"{name}: {count_parameters(model):,} params")
        x = torch.randn(2, 1, 1024)
        y = model(x)
        print(f"  Input: {x.shape} → Output: {y.shape}")
