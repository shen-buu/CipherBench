"""
模型定义 — 单通道1D-CNN 与多通道(Raw+Diff+FFT)1D-CNN
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
from config import *


class ConvBlock(nn.Module):
    """1D Conv → BN → ReLU → MaxPool"""

    def __init__(self, in_ch, out_ch, kernel=3, pool=2, dropout=0.0):
        super().__init__()
        self.conv = nn.Conv1d(in_ch, out_ch, kernel_size=kernel,
                              padding=kernel // 2, bias=False)
        self.bn = nn.BatchNorm1d(out_ch)
        self.pool = nn.MaxPool1d(pool)
        self.dropout = nn.Dropout(dropout) if dropout > 0 else nn.Identity()

    def forward(self, x):
        return self.dropout(self.pool(F.relu(self.bn(self.conv(x)))))


class SingleChannelCNN(nn.Module):
    """单通道1D-CNN — 标准基线 (对应 B4)"""

    def __init__(self, num_classes=NUM_CLASSES, dropout1=0.3, dropout2=0.3):
        super().__init__()
        self.conv1 = ConvBlock(1, 64, kernel=3, pool=2)
        self.conv2 = ConvBlock(64, 128, kernel=3, pool=2)
        self.conv3 = ConvBlock(128, 256, kernel=3, pool=2)
        self.conv4 = ConvBlock(256, 256, kernel=3, pool=2)

        self.gap = nn.AdaptiveAvgPool1d(1)

        # 计算feature map大小
        self.fc1 = nn.Linear(256, 256)
        self.dropout1 = nn.Dropout(dropout1)
        self.fc2 = nn.Linear(256, 128)
        self.dropout2 = nn.Dropout(dropout2)
        self.classifier = nn.Linear(128, num_classes)

    def forward(self, x):
        # x: [B, 1, 1024]
        x = self.conv1(x)
        x = self.conv2(x)
        x = self.conv3(x)
        x = self.conv4(x)
        x = self.gap(x).squeeze(-1)
        x = F.relu(self.fc1(x))
        x = self.dropout1(x)
        x = F.relu(self.fc2(x))
        x = self.dropout2(x)
        return self.classifier(x)


class MultiChannelCNN(nn.Module):
    """
    三通道1D-CNN (V18-Titan)
    通道: Raw + Diff + FFT Magnitude
    """

    def __init__(self, num_classes=NUM_CLASSES, channels=CNN_CHANNELS,
                 kernel=CNN_KERNEL, pool=CNN_POOL,
                 dropout1=DROPOUT1, dropout2=DROPOUT2):
        super().__init__()
        self.channels_per = [c // 2 for c in channels]  # 每通道half filters

        # Raw通道
        self.raw_conv1 = ConvBlock(1, self.channels_per[0], kernel, pool)
        self.raw_conv2 = ConvBlock(self.channels_per[0], self.channels_per[1], kernel, pool)
        self.raw_conv3 = ConvBlock(self.channels_per[1], self.channels_per[2], kernel, pool)
        self.raw_conv4 = ConvBlock(self.channels_per[2], self.channels_per[3], kernel, pool)

        # Diff通道
        self.diff_conv1 = ConvBlock(1, self.channels_per[0], kernel, pool)
        self.diff_conv2 = ConvBlock(self.channels_per[0], self.channels_per[1], kernel, pool)
        self.diff_conv3 = ConvBlock(self.channels_per[1], self.channels_per[2], kernel, pool)
        self.diff_conv4 = ConvBlock(self.channels_per[2], self.channels_per[3], kernel, pool)

        # FFT通道 (输入: FFT幅值, 前512点)
        self.fft_conv1 = ConvBlock(1, self.channels_per[0], kernel, pool)
        self.fft_conv2 = ConvBlock(self.channels_per[0], self.channels_per[1], kernel, pool)
        self.fft_conv3 = ConvBlock(self.channels_per[1], self.channels_per[2], kernel, pool)
        self.fft_conv4 = ConvBlock(self.channels_per[2], self.channels_per[3], kernel, pool)

        self.gap = nn.AdaptiveAvgPool1d(1)

        # 融合层: 3通道 × channels_per[-1]
        fused_dim = 3 * self.channels_per[3]
        self.fc1 = nn.Linear(fused_dim, FC_DIMS[0])
        self.dropout1 = nn.Dropout(dropout1)
        self.fc2 = nn.Linear(FC_DIMS[0], FC_DIMS[1])
        self.dropout2 = nn.Dropout(dropout2)
        self.classifier = nn.Linear(FC_DIMS[1], num_classes)

        self._init_weights()

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Conv1d):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
            elif isinstance(m, nn.BatchNorm1d):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)
            elif isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight)
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)

    def _raw_channel(self, x):
        """Raw字节通道"""
        return self.raw_conv4(self.raw_conv3(self.raw_conv2(self.raw_conv1(x))))

    def _diff_channel(self, x):
        """差分通道"""
        diff = x[:, :, 1:] - x[:, :, :-1]
        diff = F.pad(diff, (0, 1))  # pad to original length
        return self.diff_conv4(self.diff_conv3(self.diff_conv2(self.diff_conv1(diff))))

    def _fft_channel(self, x):
        """频域幅值通道"""
        # x: [B, 1, 1024]
        fft = torch.fft.rfft(x.squeeze(1))  # [B, 513]
        mag = torch.abs(fft).unsqueeze(1)    # [B, 1, 513]
        # 取前512点
        mag = mag[:, :, :512]
        return self.fft_conv4(self.fft_conv3(self.fft_conv2(self.fft_conv1(mag))))

    def forward(self, x):
        # x: [B, 1, 1024]
        raw_out = self.gap(self._raw_channel(x)).squeeze(-1)
        diff_out = self.gap(self._diff_channel(x)).squeeze(-1)
        fft_out = self.gap(self._fft_channel(x)).squeeze(-1)

        # 拼接三通道
        fused = torch.cat([raw_out, diff_out, fft_out], dim=1)

        x = F.relu(self.fc1(fused))
        x = self.dropout1(x)
        x = F.relu(self.fc2(x))
        x = self.dropout2(x)
        return self.classifier(x)


class TwoChannelCNN(MultiChannelCNN):
    """双通道消融模型 (Raw + Diff, 无FFT)。

    说明：
    fused 为 [B, 256]（双通道×128），fc1 输入维度为 384；
    为保证与三通道模型同构的分类头，将融合向量零填充至 fc1.in_features。
    """

    def forward(self, x):
        raw_out = self.gap(self._raw_channel(x)).squeeze(-1)
        diff_out = self.gap(self._diff_channel(x)).squeeze(-1)
        fused = torch.cat([raw_out, diff_out], dim=1)
        if fused.size(1) < self.fc1.in_features:
            fused = torch.cat([fused, torch.zeros(
                fused.size(0), self.fc1.in_features - fused.size(1),
                device=fused.device)], dim=1)
        x = F.relu(self.fc1(fused))
        x = self.dropout1(x)
        x = F.relu(self.fc2(x))
        x = self.dropout2(x)
        return self.classifier(x)


class RawFFTChCNN(MultiChannelCNN):
    """双通道消融模型 (Raw + FFT, 无Diff)。

    说明：
    与"无Diff"语义不符）。现实现为 Raw+FFT 融合并零填充至 fc1 输入维度。
    """

    def forward(self, x):
        raw_out = self.gap(self._raw_channel(x)).squeeze(-1)
        fft_out = self.gap(self._fft_channel(x)).squeeze(-1)
        fused = torch.cat([raw_out, fft_out], dim=1)
        if fused.size(1) < self.fc1.in_features:
            fused = torch.cat([fused, torch.zeros(
                fused.size(0), self.fc1.in_features - fused.size(1),
                device=fused.device)], dim=1)
        x = F.relu(self.fc1(fused))
        x = self.dropout1(x)
        x = F.relu(self.fc2(x))
        x = self.dropout2(x)
        return self.classifier(x)


def count_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


if __name__ == "__main__":
    # Quick test
    model = MultiChannelCNN(num_classes=50)
    print(f"参数量: {count_parameters(model):,}")

    x = torch.randn(2, 1, 1024)
    y = model(x)
    print(f"Input: {x.shape} → Output: {y.shape}")
