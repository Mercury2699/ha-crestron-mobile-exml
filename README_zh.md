# Crestron Mobile EXML - Home Assistant 集成

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1.0+-brightgreen.svg)](https://www.home-assistant.io)
[![Crestron 2-Series / 3-Series / 4-Series](https://img.shields.io/badge/Crestron-2--Series%20%7C%203--Series%20%7C%204--Series-blueviolet.svg)](https://www.crestron.com)

[English Documentation](README.md)

专为快思聪（Crestron）传统及现代中控主机（2 系列如 PAC2/PAC2M/CP2E、3 系列如 CP3/MC3 以及 4 系列）打造的原生 Home Assistant 自定义集成。基于标准 **Crestron Mobile EXML 协议**（TCP 端口 **41790**），**免重编译、免 SIMPL Windows 授权、零硬件改动**即可实现现代智能家居接入与 Apple HomeKit 同步。

---

## 🌟 为什么需要这个集成？

在二手房或老房翻新中，很多家庭配备了造价高昂的 Crestron（快思聪）灯光与窗帘系统。传统快思聪接入 Home Assistant（如基于 XSIG 的方案）存在极高门槛：
1. **必须拥有 Crestron 认证工程师账号与软件授权**：需要 SIMPL Windows、D3Pro、VTPro-e 等专用闭源工具。
2. **需要重新编译固件程序**：必须在 SIMPL 中引入集成模块，重新编译 `.spz` 固件并刷写进主机。如果原有工程源码丢失，几乎无法接入。
3. **官方 Crestron Home 方案不支持老设备**：Crestron Home（OS3/OS4）仅支持新一代主机，不支持广泛装机的 2 系列/3 系列主机。

**本集成彻底解决了这一痛点：**
- **免二次编译（Zero-Recompile）：** 直接利用快思聪官方移动端 App（Crestron Mobile / Crestron Mobile Pro）在主机上开启的 EXML 服务（默认 41790 端口）。原有系统无须变动任何代码！
- **本地实时推送（`local_push`）：** 基于长连接 TCP 通信，实体状态变更实时推送到 Home Assistant（延迟低于 50ms），无轮询负担。
- **精准调光拟合（Simulated Dimming Ramp）：** 针对传统快思聪 Mobile 界面通常仅提供调光 Up/Down 维持信号的机制，集成内置了高精度时间斜率模型，可在 Home Assistant 与 Apple HomeKit 中提供原生 0%~100% 亮度无级拖动滑条。
- **电动窗帘/百叶窗支持：** 支持 16 位模拟 Join 点（0~65535 自动换算为 0%~100% 比例反馈与控制），并兼容 Open/Close/Stop 脉冲控制。
- **自动化配置提取工具：** 内置 `tools/extract_crestron_config.py`，可直接解析从快思聪主机 FTP 导出的 iPad/iPhone 项目 XML 页面，自动生成可直接粘贴的 YAML 配置。

---

## 📋 功能特性

- [x] **开关与无级调光灯光**：支持单点 Toggle 反馈、升降调光、多联伴随点位联动。
- [x] **调光关断防反弹机制（Fade-Out Guard）**：有效消除快思聪硬件渐暗关灯期间因状态延迟引起的状态回弹与闪烁。
- [x] **电动窗帘/遮阳帘**：双向百分比位置控制与开/关/停操作。
- [x] **断线自动重连与心跳保活**：底层看门狗机制，网络短暂波动自动静默恢复。
- [x] **原生支持 Apple Home / Siri 与语音助手**：配合 HomeKit Bridge 即可在 iPhone、iPad、Mac、Apple Watch 上用家庭 App 和 Siri 控制。

---

## 📥 安装方式

### 方式 1：通过 HACS 安装（推荐）

1. 进入 **Home Assistant** -> **HACS** -> **Integrations（集成）**。
2. 点击右上角菜单 `⋮` -> **Custom repositories（自定义存储库）**。
3. 填入仓库地址 `https://github.com/Mercury2699/ha-crestron-mobile-exml`，类别选择 **Integration**，点击 **Add**。
4. 在集成列表中搜索 **Crestron Mobile EXML**，点击 **Download**，随后重启 Home Assistant。

### 方式 2：手动安装

1. 从 GitHub 仓库下载最新源码。
2. 将 `custom_components/crestron_mobile_exml` 目录复制到 Home Assistant 的配置目录下的 `custom_components/` 文件夹中：
   ```
   config/
   └── custom_components/
       └── crestron_mobile_exml/
           ├── __init__.py
           ├── const.py
           ├── light.py
           ├── cover.py
           └── manifest.json
   ```
3. 重启 Home Assistant。

---

## ⚙️ YAML 配置说明

在 Home Assistant 的 `configuration.yaml` 中加入配置：

```yaml
crestron_mobile_exml:
  host: 192.168.1.50         # 快思聪主机局域网 IP
  port: 41790                # EXML 服务端口（默认 41790）
  passcode: "1234"           # Crestron Mobile 访问密码（出厂或常用为 1234）

  lights:
    # 1. 调光灯（支持开关与升降按键模拟百分比调光）
    - name: "客厅主灯"
      unique_id: "crestron_living_room_main"
      toggle_join: 21          # 开关状态/切换数字 Join 点
      up_join: 22              # 调亮持续 Join 点
      down_join: 23            # 调暗持续 Join 点
      ramp_time: 5.0           # 0% 到 100% 的全行程调光时间（秒，默认 5.0）

    # 2. 多联/双控灯具（带有伴随反馈与控制点位）
    - name: "厨房筒灯"
      unique_id: "crestron_kitchen_potlights"
      toggle_join: 31
      up_join: 32
      down_join: 33
      companion_toggle_joins: [34, 37]
      companion_up_joins: [35, 38]
      companion_down_joins: [36, 39]

    # 3. 普通非调光开关回路
    - name: "玄关射灯"
      unique_id: "crestron_foyer_light"
      toggle_join: 50

  covers:
    # 电动窗帘（支持模拟位置与开/关/停）
    - name: "主卧窗帘"
      unique_id: "crestron_master_bedroom_shade"
      analog_join: 10          # 16 位模拟 Join 点 (0..65535)
      open_join: 101           # 可选：开帘数字脉冲 Join 点
      close_join: 102          # 可选：关帘数字脉冲 Join 点
      stop_join: 103           # 可选：停止数字脉冲 Join 点
```

### 参数字典

#### 主机配置 (`crestron_mobile_exml`)

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|-----------|------|----------|---------|-------------|
| `host` | 字符串 | **是** | — | 快思聪中控主机局域网 IP 地址。 |
| `port` | 整数 | 否 | `41790` | Crestron Mobile 通信端口。 |
| `passcode` | 字符串 | 否 | `"1234"` | 移动端连接口令。 |
| `lights` | 列表 | 否 | `[]` | 配置的灯光实体列表。 |
| `covers` | 列表 | 否 | `[]` | 配置的窗帘实体列表。 |

#### 灯光参数 (`lights`)

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|-----------|------|----------|---------|-------------|
| `name` | 字符串 | **是** | — | 灯光友好显示名称。 |
| `toggle_join` | 整数 | **是** | — | 主要开关/状态反馈数字 Join 点。 |
| `unique_id` | 字符串 | 否 | 自动生成 | 实体唯一 ID（用于在 HA 界面中修改实体名或分配区域）。 |
| `up_join` | 整数 | 否 | `None` | 调亮持续保持数字 Join 点。 |
| `down_join` | 整数 | 否 | `None` | 调暗持续保持数字 Join 点。 |
| `ramp_time` | 浮点数 | 否 | `5.0` | 从最暗到最亮所需的全程升温时间（秒）。 |
| `companion_toggle_joins`| 整数列表 | 否 | `[]` | 关联/双控开关反馈点位（任一为真即判定灯开）。 |
| `companion_up_joins` | 整数列表 | 否 | `[]` | 联动调亮信号点位。 |
| `companion_down_joins` | 整数列表 | 否 | `[]` | 联动调暗信号点位。 |
| `linked_off_joins` | 整数列表 | 否 | `[]` | 关灯时同步脉冲关断的其他关联点位。 |

#### 窗帘参数 (`covers`)

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|-----------|------|----------|---------|-------------|
| `name` | 字符串 | **是** | — | 窗帘友好显示名称。 |
| `analog_join` | 整数 | **是** | — | 16 位模拟位置 Join 点（0~65535）。 |
| `unique_id` | 字符串 | 否 | 自动生成 | 实体唯一 ID。 |
| `open_join` | 整数 | 否 | `None` | 数字开帘脉冲 Join 点。 |
| `close_join` | 整数 | 否 | `None` | 数字关帘脉冲 Join 点。 |
| `stop_join` | 整数 | 否 | `None` | 数字停止脉冲 Join 点。 |

---

## 🛠️ 快速提取点位配置

如果你没有工程图纸或点位表，可以直接从快思聪主机内置的 Web 目录下载移动工程文件：

### 1. 使用 FTP 导出工程文件

大部分快思聪主机内置了 FTP 服务（端口 21）：
```bash
ftp 192.168.1.50
```
进入以下路径找到 XML 界面文件：
- 2 系列主机通常位于 `/HTML/iPad/` 或 `/HTML/iPhone/`
- 下载所有 `.xml` 文件或 `.zip` 压缩包。

### 2. 运行解析脚本自动生成 YAML

```bash
# 解析解压后的 XML 目录
python3 tools/extract_crestron_config.py --dir /path/to/extracted/ipad_project/

# 或直接解析 zip 压缩包
python3 tools/extract_crestron_config.py --zip /path/to/Crestron_iPad_Project.zip
```
脚本将自动解析每个灯光与窗帘的控制 Join 点，并输出格式化好的 YAML 配置块，直接复制进 `configuration.yaml` 即可。

---

## ❓ 常见问题 (FAQ)

### 1. 本集成与原来的快思聪墙面按键面板、中控屏冲突吗？
**完全不冲突。** 快思聪的核心架构是多客户端共享状态机制。无论是墙面物理按键、Crestron 触摸屏、官方 App 还是 Home Assistant，状态都是双向实时同步更新的。

### 2. 如何接入 Apple Home（家庭 App）与 Siri？
在 Home Assistant 中启用官方的 **HomeKit Bridge（HomeKit 桥接）** 集成，将此集成生成的 `light` 和 `cover` 实体添加进桥接。随后使用 iPhone 扫描配对码，即可在 Apple 设备上获得极速的原生控制体验。

---

## 🛡️ 安全建议

- 请始终将快思聪主机置于家庭局域网受保护的独立 IoT VLAN 或子网内。
- **严禁直接将 41790 端口或 21 端口映射到公网 IPv4。** 远程访问推荐使用 Home Assistant Cloud、WireGuard VPN 或 Apple 现成的 HomePod/Apple TV 家庭中枢。

---

## 📄 开源许可证

本项目采用 [Apache License 2.0](LICENSE) 协议开源。

---

## ⚠️ 免责声明

本项目为开源社区独立项目，与 **Crestron Electronics, Inc.** 无任何从属、赞助或合作关系。*Crestron*、*SIMPL*、*D3Pro*、*Cresnet* 及 *Crestron Mobile* 均为 Crestron Electronics, Inc. 的商标或注册商标。
