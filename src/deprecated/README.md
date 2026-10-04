# deprecated

已损坏或过时的脚本,仅作历史参考,**不要使用**:

- `main.py`:旧 tkinter 界面。已损坏(相对导入错误、接口签名过时),被 `src/webui.py` 取代。
- `split.py` / `split.sh`:音频切分工具,针对 `music/*.wav` 输出编写,与当前 `.ogg` 流程不匹配;且依赖 grep/sed,Windows 原生不可用。
