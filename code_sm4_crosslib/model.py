"""
CNN模型 - SM4实现指纹识别 (独立副本, 避免跨目录config冲突)
"""
import torch
import torch.nn as nn
import torch.nn.functional as F

# 本地配置常量(不依赖config.py避免导入冲突)
CNN_CHANNELS = [64, 128, 256, 256]
CNN_KERNEL = 3
CNN_POOL = 2
FC_DIMS = [256, 128]
DROPOUT1 = 0.5
DROPOUT2 = 0.3


class ConvBlock(nn.Module):
    def __init__(self, in_ch, out_ch, kernel=3, pool=2, dropout=0.0):
        super().__init__()
        self.conv = nn.Conv1d(in_ch, out_ch, kernel_size=kernel,
                              padding=kernel // 2, bias=False)
        self.bn = nn.BatchNorm1d(out_ch)
        self.pool = nn.MaxPool1d(pool)
        self.dropout = nn.Dropout(dropout) if dropout > 0 else nn.Identity()

    def forward(self, x):
        return self.dropout(self.pool(F.relu(self.bn(self.conv(x)))))


class MultiChannelCNN(nn.Module):
    """三通道1D-CNN (Raw + Diff + FFT Mag)"""
    def __init__(self, num_classes=5, channels=None, kernel=CNN_KERNEL,
                 pool=CNN_POOL, dropout1=DROPOUT1, dropout2=DROPOUT2):
        super().__init__()
        if channels is None:
            channels = CNN_CHANNELS
        ch = [c // 2 for c in channels]  # half per channel

        # Raw
        self.raw_conv1 = ConvBlock(1, ch[0], kernel, pool)
        self.raw_conv2 = ConvBlock(ch[0], ch[1], kernel, pool)
        self.raw_conv3 = ConvBlock(ch[1], ch[2], kernel, pool)
        self.raw_conv4 = ConvBlock(ch[2], ch[3], kernel, pool)

        # Diff
        self.diff_conv1 = ConvBlock(1, ch[0], kernel, pool)
        self.diff_conv2 = ConvBlock(ch[0], ch[1], kernel, pool)
        self.diff_conv3 = ConvBlock(ch[1], ch[2], kernel, pool)
        self.diff_conv4 = ConvBlock(ch[2], ch[3], kernel, pool)

        # FFT
        self.fft_conv1 = ConvBlock(1, ch[0], kernel, pool)
        self.fft_conv2 = ConvBlock(ch[0], ch[1], kernel, pool)
        self.fft_conv3 = ConvBlock(ch[1], ch[2], kernel, pool)
        self.fft_conv4 = ConvBlock(ch[2], ch[3], kernel, pool)

        self.gap = nn.AdaptiveAvgPool1d(1)
        fused_dim = 3 * ch[3]
        self.fc1 = nn.Linear(fused_dim, FC_DIMS[0])
        self.dropout1 = nn.Dropout(dropout1)
        self.fc2 = nn.Linear(FC_DIMS[0], FC_DIMS[1])
        self.dropout2 = nn.Dropout(dropout2)
        self.classifier = nn.Linear(FC_DIMS[1], num_classes)

    def _raw_channel(self, x):
        return self.raw_conv4(self.raw_conv3(self.raw_conv2(self.raw_conv1(x))))

    def _diff_channel(self, x):
        diff = x[:, :, 1:] - x[:, :, :-1]
        diff = F.pad(diff, (0, 1))
        return self.diff_conv4(self.diff_conv3(self.diff_conv2(self.diff_conv1(diff))))

    def _fft_channel(self, x):
        fft = torch.fft.rfft(x.squeeze(1))
        mag = torch.abs(fft).unsqueeze(1)[:, :, :512]
        return self.fft_conv4(self.fft_conv3(self.fft_conv2(self.fft_conv1(mag))))

    def forward(self, x):
        raw_out = self.gap(self._raw_channel(x)).squeeze(-1)
        diff_out = self.gap(self._diff_channel(x)).squeeze(-1)
        fft_out = self.gap(self._fft_channel(x)).squeeze(-1)
        fused = torch.cat([raw_out, diff_out, fft_out], dim=1)
        x = F.relu(self.fc1(fused))
        x = self.dropout1(x)
        x = F.relu(self.fc2(x))
        x = self.dropout2(x)
        return self.classifier(x)


def count_parameters(model):
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


class TwoChannelCNN(MultiChannelCNN):
    """消融用: Raw+Diff 双通道"""
    def forward(self, x):
        raw_out = self.gap(self._raw_channel(x)).squeeze(-1)
        diff_out = self.gap(self._diff_channel(x)).squeeze(-1)
        fused = torch.cat([raw_out, diff_out], dim=1)
        pad_dim = self.fc1.in_features - fused.size(1)
        if pad_dim > 0:
            fused = torch.cat([fused, torch.zeros(fused.size(0), pad_dim, device=fused.device)], dim=1)
        x = F.relu(self.fc1(fused))
        x = self.dropout1(x)
        x = F.relu(self.fc2(x))
        x = self.dropout2(x)
        return self.classifier(x)
