# ductgen

<div align="center">

<img src="icon.png" alt="ductgen" width="420">

**参数化的 3D 打印涵道四轴机架生成器**

[![许可证: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![SolidWorks](https://img.shields.io/badge/SolidWorks-2025-red)](https://www.solidworks.com/)
[![build123d](https://img.shields.io/badge/build123d-0.9-orange)](https://github.com/gumyr/build123d)
[![CI](https://github.com/jackgibbons85/ductgen/actions/workflows/ci.yml/badge.svg)](https://github.com/jackgibbons85/ductgen/actions/workflows/ci.yml)

输入桨的尺寸、电机和你打印床的尺寸。它从正确的空气动力学得出涵道截面，把圆环切成仍然放得下的最少块数，并生成 SLDPRT、STEP 和 STL 零件。

[快速开始](#快速开始) • [功能特性](#功能特性) • [安装](#安装) • [使用方法](#使用方法) • [贡献](#贡献) • [文档](#文档)

**[English](README.md)** | **[简体中文](README.zh-CN.md)** | **[Українська](README.uk.md)**

</div>

---

> [!NOTE]
> **当前进展**
>
> 这个工具是我根据自己那台 13 英寸涵道四轴的实测数据做的，所以代码里的每一个默认值都是从那台真机上量下来的。设计部分（`preview`、`section`、`layers`、`report`）只需要 numpy 和 matplotlib，在任何系统上都能跑。SolidWorks 后端只在 Windows 上、SolidWorks 2025 修订版 33.4.1 中测试过。build123d 后端在任何能跑 Python 的地方都能用。
>
> 装配体的零部件目前只按变换摆放，没有添加配合，涵道在 CAD 里仍是实心的，还没有做减重。详见[路线图](#路线图)。

---

## 快速开始

```bash
git clone https://github.com/jackgibbons85/ductgen
cd ductgen
install.bat
python -m ductgen preview -p presets/13in_a1.json
```

这会输出一张预览 PNG 和一份完整报告，全程不碰 CAD。之后可以双击 `ductgen-gui.pyw` 打开桌面窗口，或者运行 `python -m ductgen build -p presets/13in_a1.json -o out/13in` 来生成实体。

## 功能特性

### 几何

改一个输入值，工具会算出它意味着什么，并在数字对不上时直接告诉你。

- **桨直径决定涵道内径**，按你要求的桨尖间隙。喉部、弦长、唇口半径和桨盘平面深度都按 D 缩放。
- **kV 乘电芯数得到转速，再得到桨尖马赫数。** 13 英寸预设在 9,576 转下是 0.48 马赫。超过 0.6 它会提示。
- **唇口半径决定涵道外径。** 6% D 的喇叭口需要 36 毫米的径向空间，之后才谈得上还剩多少结构。如果你要在 20 毫米壁厚里塞下它，截面会自交，所以 `duct_od` 会直接解决这个冲突，而不是让旋转特征失败，报告里会说明圆环变宽了以及为什么。
- **扩压角决定扩张比 sigma，进而决定理想推力增益**，(2σ)^(1/3)，即等轴功率下涵道相对开放桨的静态比值。
- **截面加打印机决定质量**，按 3 层外壁和 15% 填充计算。13 英寸涵道算下来单环 965 克，四个共 3.86 千克，这是故意让规则判不通过的。正是这个数字决定了涵道到底值不值得带上天。

每条规则都会以 OK、WARN 或 FAIL 的形式对照它的要求给出结果。

![四面板预览](docs/preview-derived.png)
*`preview` 的输出：涵道截面、俯视图、打印床排布和规则表，全在一张 PNG 里*

### 为打印床做分割

这部分不用工具的话就得靠手工来做。

- **能放下的最少分段数。** 弧形扇区会在平面内的每个旋转角度上测试，所以 256 毫米的打印床沿对角线大约能放下 345 毫米的零件。13 英寸涵道的结果是 4 段，每段 89 度，207 x 207 x 99 毫米，占打印床的 85%，整机一共 16 段打印弧。3.5 英寸的圆环可以整圈打印。
- **接缝避开支柱根部。** 接缝相位的选取会最大化到最近定子的角度间隙，这样就不会有胶缝落在电机载荷进入圆环的位置。
- **一个零件，N 次旋转。** 每个分段都相对 Front 基准面对称旋转生成，一端是上半搭接，另一端是下半搭接，因此同一个圆环的所有分段都是同一个零件。一个文件打印 16 次即可。
- **已内置打印床配置**，覆盖 Bambu A1、A1 mini、X1C/P1S、Prusa MK4、Prusa XL、Ender 3、K1 Max、Voron 2.4 350 和 Elegoo Neptune 4，位于 `presets/printers.json`。

![同一个零件的四份副本旋转后闭合成环](docs/ring_closure.png)
*`analysis/verify_ring.py` 会重新导入生成的 STL，旋转 N 份副本，并确认圆环在四个高度上都以零角度间隙闭合*

### 两个 CAD 后端

两者使用同样的 `Frame`、`RingPlan` 和 `segment_features()`，因此所有设计决策都是共用的，区别只在实体建模。在 13 英寸预设上，两者的零件体积吻合到约 0.01%，这个差距来自 SolidWorks 与 OCCT 通过同样的喇叭口点位做样条拟合的不同。

|  | SolidWorks（`sw`，默认） | build123d（`b3d`） |
| --- | --- | --- |
| **需要** | 许可证、Windows、pywin32 | `pip install build123d` |
| **原生文件** | SLDPRT 和 SLDASM，可编辑的特征树 | 无，只有内核几何 |
| **导出** | STEP、STL | STEP、STL |
| **装配** | 零部件摆放在 SLDASM 中 | 零部件合成一个 compound |
| **速度** | 较慢，每个特征都是一次 COM 往返调用 | 整机 61 个零部件，约 9 秒 |

想要一棵能继续手工编辑的特征树就用 SolidWorks。想在没有 CAD 授权的机器上、在 CI 里或在 Linux 上拿到几何就用 build123d。

### 桌面窗口与 SolidWorks 按钮

- **规则实时更新。** 改动桨、kV 或打印床，分段数、床上尺寸以及每一条 OK/WARN/FAIL 都会随着输入即时刷新。
- **工具栏按钮。** 同一个窗口可以放到 SolidWorks 的工具栏上，零件就直接在你已经打开的会话里生成。配置大约需要三十秒，见 [macro/README.md](macro/README.md)。
- **预设可进可出。** 参数可以读写 JSON，也可以在命令行用点号键覆盖任意一项。

### 每个预设都会跑的检查

- **圆环闭合。** 圆环必须在每个高度上都闭合满 360 度。
- **碳管通路。** 每根碳纤维管都必须能顺畅穿过打印件。正是这一项能抓出打在半搭接错误一侧的孔，或者某个接头漏掉了直穿而过的碳管孔。
- **孔与孔干涉。** `ductgen.clash` 检查同一零件上任意两个孔是否互相侵入。每个孔都来自不同的规则，此外没有任何机制去协调它们，正因为如此，电机螺栓曾在此前生成的每一副机架上都通到了碳管插槽里。
- **对照真机。** `presets/reference_drone3.json` 必须持续复现我实测的那副机架。

![生成的电机座与实测 STL 对照](docs/mount_fixed.png)
*四个高度上的装配体截面，以及生成的电机座（橙色）与从真机上量取的 STL（绿色）对照，13.44 cm³ 对 13.55 cm³*

### 打印方向

- **进气面朝上，每次都是。** 这样喇叭口会逐层内收，不需要支撑。倒过来打的话，唇口正好是一整片悬垂，而那恰恰是最在意形状的一个面。
- **只有一处悬垂值得一提。** 在正确方向下，唯一悬垂的内孔面是扩压段，与竖直方向成 3 度。
- **支撑极少。** 每个分段一端的半搭接凸台下方是悬空的。只给那一个面加支撑，每个零件两小块即可。

### 组装起来

- **用销，不用螺栓。** 接缝靠搭接两半各自的盲销孔定位。承力结构是碳纤维缠绕层，销子只是在缠绕过程中防止两半错位。设 `joint.stud = 0` 可以换回通孔螺栓。
- **买得到的碳管规格。** 碳管尺寸、螺栓分布和中心板都由桨推导而来，除非你手动固定；推导出的碳管会吸附到市面上真正买得到的管径上。13 英寸对应 10 毫米机臂和 20 毫米主梁，5 英寸对应 6 和 12。输出里不会出现 5.3249 毫米这种数。
- **机臂有落点。** 每个电机各有一根机臂指向机体中心，插进中心板并固定在那里，而不是在自己的涵道外一厘米处悬空收尾。这由 `rods.motor_inboard` 控制，也正是中心板相对主梁不对称的原因。

---

## 系统要求

| 部分 | 需要 | 说明 |
| --- | --- | --- |
| **设计部分** | Python 3.10+、numpy、matplotlib | `preview`、`section`、`layers`、`report`。任意系统，无需 CAD。 |
| **SolidWorks 后端** | SolidWorks 与 pywin32，Windows | 在 2025 修订版 33.4.1 上测试通过 |
| **build123d 后端** | `pip install build123d` | 任意系统。需要正常安装的 CPython 3.10 到 3.12，而不是 Windows Store 版本，因为 OCP 的 wheel 是按前者编译的。 |

---

## 安装

```bash
git clone https://github.com/jackgibbons85/ductgen
cd ductgen
install.bat
```

这会安装 numpy、matplotlib 和 pywin32。build123d 是可选的，默认不会装：

```bash
pip install build123d
```

---

## 使用方法

### 命令行

```bash
python -m ductgen preview -p presets/13in_a1.json           # PNG 和报告，不需要 CAD
python -m ductgen report  -p presets/reference_drone3.json  # 只要数字
python -m ductgen section -p presets/13in_a1.json           # 只出涵道子午面截面
python -m ductgen layers  -p presets/13in_a1.json           # 分层透明 PNG
python -m ductgen build   -p presets/13in_a1.json -o out/13in
```

用点号键覆盖任意参数：

```bash
python -m ductgen preview -p presets/13in_a1.json prop.diameter_in=5 printer.bed_x=180
```

`dump` 会把整套参数以 JSON 打印出来，`set` 则把它写回预设文件。

### 用 SolidWorks 构建

```bash
python -m ductgen build -p presets/13in_a1.json -o out/13in
python -m ductgen build -p presets/13in_a1.json -o out/13in --hidden     # 不显示 SolidWorks 窗口
python -m ductgen build -p presets/13in_a1.json -o out/13in --keep-open  # 保持零件打开
```

### 用 build123d 构建

```bash
pip install build123d
python -m ductgen build -p presets/13in_a1.json -o out/b3d --backend b3d
```

### 输出

```
<name>_duct_segment*.SLDPRT / .STEP / .STL   圆环，每种碳管变体一个文件
<name>_motor_mount.SLDPRT / .STEP / .STL     x 4
<name>_strut.SLDPRT / .STEP / .STL           每环 x 4
<name>_connector.SLDPRT / .STEP / .STL
<name>_center_plate.SLDPRT / .STEP / .STL
<name>_rod_*.SLDPRT / .STEP                  每种碳管长度一个
<name>_frame.SLDASM / .STEP / .STL           所有零部件均已摆放
<name>_placement.json    每份副本放在哪里：涵道、x、y、旋转角
<name>_report.txt        几何、性能、规则、下料表、五金件
<name>_params.json       生成这一版的确切输入
```

报告里还包含碳管下料表和螺栓数量。在 13 英寸预设上是 40 根 2.5 毫米接缝销和 16 颗 M3 电机螺栓。

### 测试

```bash
python tests/test_geometry.py
```

不需要 CAD。它检查真正要紧的不变量：子午线永不自交、唇口始终装得进壁厚、N 个分段恰好铺满 360 度、接缝绝不落在支柱根部、更小的打印床绝不会得出更少的分段、支柱插槽始终留有材料余量、每根碳管都有通路且上方有螺丝、碳管落在买得到的规格上，以及参考预设仍然复现实测的那台机器。如果装了 build123d，相关用例也会一起跑。CI 在每次 push 时运行整套测试并上传渲染好的预览图。

---

## 贡献

欢迎各种形式的贡献，无论是缺陷报告、功能建议、修复还是新的预设。

### 如何贡献

1. **报告问题。** 发现 bug 了？[提交 issue](https://github.com/jackgibbons85/ductgen/issues/new)
2. **提出功能建议。** 有想法？[给我发邮件](https://github.com/jackgibbons85/ductgen/discussions)
3. **发一个预设过来。** 一份能用的打印机配置或机架预设是实打实的帮助。
4. **写代码。** Fork、开分支，并确保 `python tests/test_geometry.py` 仍然通过。

### 需要帮助的领域

- **Linux 和 macOS 测试**，针对 build123d 后端，它是唯一能在那些系统上运行的后端
- **更老的 SolidWorks 版本。** COM 调用是按 2025 的预期写死的，尤其 `FeatureCut4` 的参数个数在不同版本之间变过
- **打印机配置。** 为 `presets/printers.json` 补充更多条目
- **机架预设**，最好像 `reference_drone3` 那样背后有实测数据
- **接缝类型。** `dovetail` 和 `butt_pin` 已声明但尚未实现
- **翻译。** 目前这份 README 有英文、简体中文和乌克兰文

---

## 文档

- **[REFERENCE.md](REFERENCE.md)** - 所有默认值追溯到的那台实测机器
- **[macro/README.md](macro/README.md)** - 如何把 ductgen 放到 SolidWorks 工具栏按钮上
- **[DEVLOG.md](DEVLOG.md)** - 开发日志，包括遇到的 SolidWorks API 问题和解决过程

### SolidWorks 笔记

这里遇到过一些问题

- 后期绑定的 COM 会把 SolidWorks 的方法变成属性，于是 `doc.GetTitle` 返回的是字符串而不是可调用对象。`swapi.module()` 会在首次运行时用 makepy 注册类型库，之后一切都走生成的包装类。
- `IFeatureManager::FeatureCut4` 在 2025 里接收 27 个参数，而不是大多数已发布示例里的 24 个。多出来的三个是 `T0`、`StartOffset` 和 `FlipStartOffset`。
- `InsertRefPlane` 返回的是 `IRefPlane`，而 `ISketch` 根本没有名称。这两个名称都得改从 `FeatureByPositionReverse(0)` 获取。
- `SaveAs3` 的 Errors 和 Warnings 参数是输入输出型的，所以必须传进去，而不只是读回来。
- 必须设置 `swSTLDontTranslateToPositive`，否则导出器会把每个零件平移到正卦限，从而丢掉摆放位置。`swSTLShowInfoOnSave` 必须关掉，否则模态对话框会把整个流程卡住。
- 倾斜基准面是这套 API 里最脆弱的部分，因此构建过程完全避开了它们。`build_sw.py` 的模块 docstring 里写了让这一点成为可能的对称旋转技巧。

---

## 技术

### 核心

- **Python 3.10+** - 整个引擎
- **numpy** - 几何计算
- **matplotlib** - 预览、截面和分层渲染
- **Tkinter / ttk** - 桌面窗口

### CAD

- **SolidWorks 2025 API** - 通过 COM 驱动，pywin32 前期绑定
- **build123d 0.9** - 基于 OCCT 的 Python CAD，无需许可证的后端
- **VBA** - 一个很薄的启动器，让工具能待在 SolidWorks 工具栏上

### 工具链

- **GitHub Actions** - 每次 push 都运行几何测试并渲染每个预设

### 目录结构

```
ductgen/
  params.py      输入、推导几何、推导性能、设计规则
  profile.py     涵道子午面截面，预览和两个 CAD 构建器共用同一份定义，
                 所以 PNG 里画的就是实际被旋转生成的东西
  segment.py     打印床分割与接缝相位
  layout3d.py    每个零件实例的位置，以及碳管走向
  clash.py       孔与孔之间的干涉检查
  bridge.py      两个后端共用的几何辅助函数
  preview.py     四面板 PNG：截面、俯视图、打印床、规则表
  swapi.py       SolidWorks COM 包装层（单位、前期绑定、基准面查找）
  build_sw.py    SolidWorks 中的涵道分段和电机座
  build_parts.py SolidWorks 中的接头、中心板和碳管
  build_asm.py   SolidWorks 装配体
  build_b3d.py   用 build123d 生成同样的零件和装配
  gui.py         桌面窗口，规则实时刷新
  cli.py         命令行
analysis/        STL 逆向脚本，圆环和装配检查
presets/         reference_drone3（实测）、13in_a1、cinewhoop_35、printers
macro/           DuctGen.bas，SolidWorks 工具栏启动器
tests/           几何不变量测试，不需要 CAD
```

---

## 许可证

MIT。详见 [LICENSE](LICENSE)。

---

## 致谢

- gumyr 的 [build123d](https://github.com/gumyr/build123d)，它让无许可证后端成为可能
- SolidWorks API 文档，以及那些填补了文档空白的论坛帖子
- 这里的每一个默认值都追溯到一台真实的 13 英寸机架，记录在 [REFERENCE.md](REFERENCE.md)

---

## 联系方式

Jack Gibbons, [jackgibbons@artyom.us](mailto:jackgibbons@artyom.us)

缺陷和功能请求建议[提 issue](https://github.com/jackgibbons85/ductgen/issues/new) 而不是发邮件，这样答案会留在下一个人能找到的地方。

<div align="center">

**如果 ductgen 对你有帮助，欢迎在 GitHub 上点个 star。**

</div>
