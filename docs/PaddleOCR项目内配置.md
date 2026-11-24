# PaddleOCR 项目内配置（CPU 回退 + CUDA GPU 服务）

本项目把 OCR 分成两层：主程序（Python 3.8）内置的 PaddleOCR 2.8 CPU 后端负责兜底；独立 Python 3.12 服务使用 PaddlePaddle 3.x + CUDA 12.9，优先在 NVIDIA RTX 5090 上识别。GPU 服务不可用、未安装或显存不足时，主程序自动回退 CPU，不阻断扫描流程。

## 1. 两套环境

| 用途 | 解释器 | Paddle | PaddleOCR | 模型 | 运行位置 |
| --- | --- | --- | --- | --- | --- |
| GPU 优先 | .venv-ocr-gpu（Python 3.12） | paddlepaddle-gpu 3.3.1（cu129） | 3.7.0 | PP-OCRv5_mobile_det / rec | 本机 127.0.0.1:8770 子进程 |
| CPU 回退 | 主程序 Python 3.8 | paddlepaddle 2.6.2 CPU | 2.8.1 | PP-OCRv4（项目内） | 主程序进程内 |

为什么必须是独立进程：

- RTX 5090 是 Blackwell sm_120，需要 CUDA 12.9 或 13.0 的 Paddle 3.x。
- Paddle 官方 cu129 wheel 只提供 cp39 及以上，没有主程序使用的 cp38。
- PaddleOCR 2.x 的 PP-OCRv4 模型不能直接给 PaddleOCR 3.x 使用，所以 GPU 服务单独使用 PP-OCRv5 mobile 模型。

## 2. 目录

~~~text
data/models/paddleocr/
  det/    PP-OCRv4 文字检测模型（CPU 回退）
  rec/    PP-OCRv4 文字识别模型
  cls/    文字方向分类模型

data/models/paddlex/
  ...     PaddleOCR 3.x 首次运行下载的 PP-OCRv5 mobile 模型
~~~

data/ 是运行数据目录，部署时随项目一起复制；它已在 .gitignore 中，不会进入 Git 历史。GPU 模型目录由环境变量 PADDLE_PDX_CACHE_HOME 指向 data/models/paddlex。

若换一台机器部署、data/models/paddleocr 为空，可从已安装 PaddleOCR 的缓存补齐：

~~~powershell
New-Item -ItemType Directory -Force data/models/paddleocr/det, data/models/paddleocr/rec, data/models/paddleocr/cls | Out-Null
Copy-Item "$env:USERPROFILE\.paddleocr\whl\ch_PP-OCRv4_det_infer\*" data/models/paddleocr/det -Recurse -Force
Copy-Item "$env:USERPROFILE\.paddleocr\whl\ch_PP-OCRv4_rec_infer\*" data/models/paddleocr/rec -Recurse -Force
Copy-Item "$env:USERPROFILE\.paddleocr\whl\ch_ppocr_mobile_v2.0_cls_infer\*" data/models/paddleocr/cls -Recurse -Force
~~~

## 3. 配置

配置文件：report_generator/assets/scan_recognition_config.json

~~~json
{
  "ocr": {
    "provider": "paddle",
    "lang": "ch",
    "model": "ch_PP-OCRv4",
    "det_model_dir": "data/models/paddleocr/det",
    "rec_model_dir": "data/models/paddleocr/rec",
    "cls_model_dir": "data/models/paddleocr/cls",
    "use_gpu": false,
    "gpu_service_url": "http://127.0.0.1:8770",
    "gpu_service_timeout": 180,
    "gpu_service_autostart": true,
    "gpu_service_python": ".venv-ocr-gpu/Scripts/python.exe",
    "gpu_service_script": "scripts/ocr_gpu_service.py",
    "gpu_service_cache_dir": "data/models/paddlex",
    "gpu_det_model": "PP-OCRv5_mobile_det",
    "gpu_rec_model": "PP-OCRv5_mobile_rec",
    "pdf_dpi": 300,
    "low_conf_threshold": 0.85
  }
}
~~~

- gpu_service_url 非空时，build_ocr_backend() 先构造 RemoteOcrBackend；它内部仍持有本机 CPU PaddleOCR 作为 fallback。
- gpu_service_autostart=true 时，主程序发现 8770 未监听会自动启动 .venv-ocr-gpu 子进程；设置 false 则只连接已启动的服务。
- use_gpu 只控制主程序内 PaddleOCR 2.x 的本地 GPU 开关。主程序是 CPU 版 Paddle，必须保持 false；GPU 识别由独立服务负责。
- 相对路径按项目根解析，也可写绝对路径。部署时可用 STRUCTURAL_OCR_GPU_URL / STRUCTURAL_OCR_GPU_PYTHON 覆盖地址和解释器。

## 4. 安装 GPU 环境

前置条件：Windows x64、NVIDIA 驱动支持 CUDA 12.9（本机 RTX 5090，驱动 576.88）、Python 3.12。不需要单独安装 CUDA Toolkit 或 nvcc，nvidia-cuda-runtime-cu12 等 wheel 会提供运行库。

推荐使用脚本（创建 .venv-ocr-gpu，安装 paddlepaddle-gpu 3.3.1 与 PaddleOCR 3.7.0）：

~~~powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_ocr_gpu.ps1
~~~

离线或下载很慢时，可先准备 Paddle wheel 和依赖 wheelhouse，再安装：

~~~powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_ocr_gpu.ps1 -PaddleWheel C:\downloads\paddlepaddle_gpu-3.3.1-cp312-cp312-win_amd64.whl -Wheelhouse C:\downloads\paddle_wheelhouse
~~~

手工安装等价于：

~~~powershell
py -3.12 -m venv .venv-ocr-gpu
.\.venv-ocr-gpu\Scripts\python.exe -m pip install -U pip
.\.venv-ocr-gpu\Scripts\python.exe -m pip install -r requirements-ocr-gpu.txt
~~~

requirements-ocr-gpu.txt 固定了 Paddle、PaddleOCR 和 CUDA 12.9 运行库版本。安装约 5 GB（wheel 下载约 2 GB，解压后的 .venv-ocr-gpu 约 4.9 GB），首次安装需要较长时间；Windows 注册表里若有失效代理，先设置 NO_PROXY=*。GPU 服务默认把 PADDLE_PDX_MODEL_SOURCE 设为 bos（百度 BOS 官方模型源），可用环境变量覆盖为 modelscope / huggingface / aistudio。

requirements 里还固定了 nvidia-nvjitlink-cu12==12.9.86（cufft 的依赖）。它缺失时 Paddle 会报 cusolver64_11.dll 或其依赖加载失败，表现为 GPU matmul 无法导入；补齐后 pip check 应为 No broken requirements found。

## 5. 启动、停止与校验

后台启动并等待 /health 就绪：

~~~powershell
powershell -ExecutionPolicy Bypass -File scripts\start_ocr_gpu.ps1
~~~

前台运行（调试时看日志）：

~~~powershell
powershell -ExecutionPolicy Bypass -File scripts\start_ocr_gpu.ps1 -Foreground
~~~

停止：

~~~powershell
powershell -ExecutionPolicy Bypass -File scripts\stop_ocr_gpu.ps1
~~~

日志：data/logs/ocr_gpu_service.err.log、data/logs/ocr_gpu_service.out.log、data/logs/ocr_gpu_service.pid。首次启动会下载 PP-OCRv5 mobile 模型，可能超过 300 秒；脚本会提示查看日志。

校验 GPU 矩阵运算：

~~~powershell
.\.venv-ocr-gpu\Scripts\python.exe -c "import paddle; print(paddle.__version__, paddle.device.is_compiled_with_cuda(), paddle.device.cuda.device_count()); x=paddle.ones([64,64]); y=paddle.matmul(x,x); y.numpy(); print(float(y.sum()))"
~~~

健康检查：

~~~powershell
Invoke-RestMethod http://127.0.0.1:8770/health | ConvertTo-Json -Depth 5
~~~

正常时 ready=true、gpu=true、device 含 gpu、models 显示 PP-OCRv5_mobile_det/rec。

识别单张图片：

~~~powershell
$body = @{ path = (Resolve-Path 'original_record/scanned/混凝土楼板钢筋间距原始记录.jpg').Path } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8770/ocr -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
~~~

主程序侧验证优先走 GPU：

~~~powershell
python -c "from report_generator.scan_recognition.config import Config; from report_generator.scan_recognition.ocr import build_ocr_backend; b=build_ocr_backend(Config.load()); print(type(b).__name__); print(b.recognize(r'original_record/scanned/混凝土楼板钢筋间距原始记录.jpg')[:200])"
~~~

输出类型应为 RemoteOcrBackend；若 GPU 服务不可用，会记录警告并回退 CPU，仍返回识别文本。

## 6. CPU 回退依赖

~~~powershell
python -m pip install -r requirements-scan.txt
~~~

对应版本：PaddlePaddle 2.6.2、PaddleOCR 2.8.1、PyMuPDF。

不启动 Web 后端，直接跑本地 CPU OCR：

~~~powershell
python -c "from report_generator.scan_recognition.config import Config; from report_generator.scan_recognition.ocr import build_ocr_backend; c=Config.load(); print(c.ocr_model_dirs()); b=build_ocr_backend(c); print(b.recognize(r'original_record/scanned/混凝土楼板钢筋间距原始记录.jpg')[:300])"
~~~

应能看到项目内三个模型目录，以及识别出的表格文本。

## 7. 回退规则

- gpu_service_url 为空：只使用本机 CPU PaddleOCR。
- GPU 服务未启动且 gpu_service_autostart=true：主程序尝试启动 .venv-ocr-gpu；超时或健康检查失败则回退 CPU。
- /health 返回 503（Paddle 初始化失败）时，主程序读取 error 并立即回退，不等待满 180 秒。
- /ocr 请求异常：本次回退 CPU，并暂停 GPU 30 秒，避免每个文件都卡在失败连接上。
- 回退只记录一次警告，避免日志刷屏。

## 8. 故障排查

- 报 cublas64_12.dll / cudnn64_9.dll 找不到：确认 requirements-ocr-gpu.txt 中的 nvidia-*-cu12 已安装；scripts/ocr_gpu_service.py 启动时会把 .venv-ocr-gpu/Lib/site-packages/nvidia/*/bin 加入 DLL 搜索路径。
- 报 sm_120 / GPU Compute Capability 12.0 不匹配：说明 Paddle 不是 cu129 的 3.3.1 wheel，重装 paddlepaddle-gpu==3.3.1。
- PowerShell 报“字符串缺少终止符”或“意外的标记”：.ps1 必须保存为 UTF-8 with BOM；Windows PowerShell 5.1 会把无 BOM 的 UTF-8 当 GBK 解析。
- 首次启动一直未 ready：查看 data/logs/ocr_gpu_service.err.log，通常是 PP-OCRv5 模型下载慢或网络被代理拦截。
- pip 下载大 wheel 反复停滞：用 curl --noproxy "*" 断点续传，放入 wheelhouse，再用 -Wheelhouse 安装；不要同时下载多个大文件。
- 不想用 GPU：把 gpu_service_url 设为空字符串，或把 gpu_service_autostart 设为 false 并停止服务。

## 9. 限制

- GPU 服务内部对 predict 加锁，同一时刻只处理一个文件；批量扫描会串行等待。
- 服务只监听 127.0.0.1，没有鉴权，不要暴露到局域网或公网。
- 首次运行需要联网下载 PP-OCRv5 mobile 模型；离线部署要预先复制 data/models/paddlex。
- PP-OCRv5 与 PP-OCRv4 是两套模型，CPU 回退仍使用项目内 v4 模型，识别结果可能有差异。
- 当前主程序 Python 3.8 无法直接加载 cu129 wheel；不要把 .venv-ocr-gpu 的包装进主程序环境。

## 10. 本机验证记录（2026-11-18，RTX 5090）

- .venv-ocr-gpu：Paddle 3.3.1，paddle.device.is_compiled_with_cuda()=True，cuda.device_count()=1。
- 64x64 GPU matmul 返回 262144.0；日志确认 GPU Compute Capability 12.0、Driver API 12.9、Runtime API 12.9。
- GET /health：ready=true、gpu=true、device=gpu:0、paddle=3.3.1、paddleocr=3.7.0，models 为 PP-OCRv5_mobile_det / PP-OCRv5_mobile_rec。
- POST /ocr（original_record/scanned/混凝土楼板钢筋间距原始记录.jpg）：返回 261 个文本框，首行“现浇混凝土构件钢筋间距检测记录”。
- 主程序 build_ocr_backend() 返回 RemoteOcrBackend；health 同上，recognize_items 返回 261 项，recognize() 输出带制表符的表格行。
- 停止服务后直接调用主程序：RemoteOcrBackend 自动拉起 .venv-ocr-gpu 子进程，识别仍返回 261 项。
- 把 gpu_service_url 指向未监听端口并关闭 autostart：回退 CPU PaddleOCR，日志出现“GPU OCR 不可用（<urlopen error timed out>），本次回退 CPU PaddleOCR”，仍返回识别文本。
- 后端 /api/scan/submit 实测（sample_ocr.jpg）：约 32 秒完成，状态 done，返回 261 个 OCR 文本框并经视觉模型整理为 22 列、多行构件数据；服务日志同期出现 POST /ocr 200。
- 补齐 nvidia-cusolver-cu12、nvidia-cusparse-cu12、nvidia-nvjitlink-cu12 后，.venv-ocr-gpu 的 pip check 返回 No broken requirements found；服务重启后 /health 仍为 gpu:0，/ocr 仍返回 261 项。
- PP-OCRv5 mobile 模型缓存在 data/models/paddlex，约 27.3 MB，不依赖用户目录。

## 11. 对话中的图片附件

对话页上传图片时，前端会调用 `POST /api/scan/ocr-text`，由项目 PaddleOCR（GPU 优先、CPU 回退）识别图片，然后把附件路径和识别文本一起放进输入框：

~~~text
[附件] data/uploads/...jpg

[图片 OCR 文本，已由项目 PaddleOCR 识别，可直接使用]
...
~~~

因此即使当前模型（如 qwen3.8:27b-64k）只支持文本，也能直接基于 OCR 文本继续检测流程；前端不会再自动切换到视觉模型。OCR 失败或无文字时只提示警告，附件仍保留。

DSH 的 `read_image` 工具要求模型声明图片输入；即使声明后，本机实测仍可能在附件保存完成后长时间停在 in_progress。需要读图时优先使用上面的 OCR 兜底，不要把 `read_image` 作为检测流程的必需步骤。

### 11.1 旧附件与“继续”对话

上传时的 OCR 文本只写进当次输入框。历史会话里的图片消息仍然只有一行 `[附件] data/uploads/....jpg`；用户直接说“继续”时，模型只看到这个路径，可能再次调用 `read_image`，于是又出现历史里的“读取图片识别失败”。这条失败记录是当时的工具轨迹，不会因为修复而自动消失。

现在后端在每次提交 prompt 前会检查最近 12 条用户消息和当前输入：

- 提取 `[附件]` 后的图片路径，只处理 .jpg/.jpeg/.png/.webp/.gif/.bmp/.tif/.tiff，并且必须位于项目根目录内。
- 最多取最后 3 张尚未带 OCR 标记的图片，调用项目 PaddleOCR（GPU 优先、CPU 回退），单轮 OCR 文本合计不超过 12000 字；结果按绝对路径 + mtime + 文件大小缓存，避免每轮重复识别。
- 在用户当前请求前注入“【图片附件处理 · 系统自动注入】”块，明确要求直接使用 OCR 文本、禁止调用 `read_image`，并说明旧消息里的图片读取错误是历史记录。
- 已经带 `[图片 OCR 文本，已由项目 PaddleOCR 识别]` 标记的新上传不会被重复 OCR。

实测：对旧会话 transcript 加“继续”，生成的注入块约 1296 字，包含“现浇混凝土构件钢筋间距检测记录……检测设备 钢筋测仪……”等文本；用 DeepSeek 文本模型测试 2.4 秒返回结果，未调用 `read_image`。本机 qwen3.6:35b 在该测试中 110 秒没有输出，属于模型侧停滞，不是 OCR 注入失败。当前本机 Ollama 只安装了 qwen3.6:35b；配置里的 qwen3.8:27b-64k 未安装，选中它会返回 model not found。

相关实现：`webapp/backend/routers/chat.py` 的 `_image_prompt_block()`、`_ocr_image_text()`、`_attachment_paths()`。

## 12. 与视觉模型的关系

扫描流水线在 llm.use_vision=auto 且配置了 vision_model 时，会优先让视觉模型直接看图转写；PaddleOCR 仍会先执行并将文本作为回退。若希望只用 PaddleOCR，把 llm.use_vision 设为 off，或清空 llm.vision_model 并确保 Ollama 不可用。

相关实现：

- report_generator/scan_recognition/ocr.py：PaddleOCR 后端、RemoteOcrBackend、CPU/GPU 回退
- report_generator/scan_recognition/config.py：默认配置与路径解析
- report_generator/assets/scan_recognition_config.json：运行配置
- webapp/backend/routers/scan.py：`POST /api/scan/ocr-text` 对话图片 OCR 兜底
- webapp/backend/routers/chat.py：`_image_prompt_block()` / `_ocr_image_text()` / `_attachment_paths()`，恢复旧会话时把图片 OCR 注入 prompt
- webapp/frontend/src/views/ChatView.vue：图片上传后 OCR 文本填入输入框
- scripts/ocr_gpu_service.py：GPU HTTP 服务
- scripts/setup_ocr_gpu.ps1、scripts/start_ocr_gpu.ps1、scripts/stop_ocr_gpu.ps1：安装与启停
- requirements-ocr-gpu.txt：GPU 依赖
- docs/PaddleOCR项目内配置.md：本文档
