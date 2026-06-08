"""
HEX 文件合并工具 - 图形化界面

功能：
1. 导入 APP Hex 文件（如 CheryLitePlatformLocalization.hex）
2. 导入 Boot Hex 文件（如 CheryBoot_New.hex）
3. 指定输出文件路径
4. 执行合并（CRC-32 追加 + 文件合并 + 标记字节插入）
"""

import os
import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox

from hex_merge_tool import process


class HexMergeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("HEX 文件合并工具")
        self.root.resizable(True, True)
        self.root.minsize(560, 420)

        self._build_ui()

    def _build_ui(self):
        # --- 文件选择区域 ---
        file_frame = tk.LabelFrame(self.root, text="文件选择", padx=10, pady=10)
        file_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        # Row 1: APP Hex 文件
        tk.Label(file_frame, text="APP Hex 文件:", anchor=tk.W).grid(
            row=0, column=0, sticky=tk.W, pady=4)
        self.app_entry = tk.Entry(file_frame, width=50)
        self.app_entry.grid(row=0, column=1, sticky=tk.EW, padx=(5, 5), pady=4)
        tk.Button(file_frame, text="浏览", width=6,
                  command=lambda: self._browse_hex(self.app_entry, "选择 APP Hex 文件")).grid(
            row=0, column=2, pady=4)

        # Row 2: Boot Hex 文件
        tk.Label(file_frame, text="Boot Hex 文件:", anchor=tk.W).grid(
            row=1, column=0, sticky=tk.W, pady=4)
        self.boot_entry = tk.Entry(file_frame, width=50)
        self.boot_entry.grid(row=1, column=1, sticky=tk.EW, padx=(5, 5), pady=4)
        tk.Button(file_frame, text="浏览", width=6,
                  command=lambda: self._browse_hex(self.boot_entry, "选择 Boot Hex 文件")).grid(
            row=1, column=2, pady=4)

        # Row 3: 输出文件路径
        tk.Label(file_frame, text="输出文件路径:", anchor=tk.W).grid(
            row=2, column=0, sticky=tk.W, pady=4)
        self.output_entry = tk.Entry(file_frame, width=50)
        self.output_entry.grid(row=2, column=1, sticky=tk.EW, padx=(5, 5), pady=4)
        tk.Button(file_frame, text="浏览", width=6,
                  command=self._browse_output).grid(row=2, column=2, pady=4)

        file_frame.columnconfigure(1, weight=1)

        # --- 按钮区域 ---
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)

        self.merge_btn = tk.Button(btn_frame, text="合并", width=12,
                                   command=self._on_merge)
        self.merge_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.clear_btn = tk.Button(btn_frame, text="清除", width=12,
                                   command=self._on_clear)
        self.clear_btn.pack(side=tk.LEFT)

        # --- 日志输出区域 ---
        log_frame = tk.LabelFrame(self.root, text="日志", padx=5, pady=5)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 10))

        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=12, state=tk.DISABLED, wrap=tk.WORD,
            font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _browse_hex(self, entry_widget, title):
        """打开文件对话框选择 .hex 文件"""
        filepath = filedialog.askopenfilename(
            title=title,
            filetypes=[("HEX 文件", "*.hex"), ("所有文件", "*.*")])
        if filepath:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, filepath)

    def _browse_output(self):
        """打开文件对话框选择输出路径"""
        filepath = filedialog.asksaveasfilename(
            title="选择输出文件路径",
            defaultextension=".hex",
            filetypes=[("HEX 文件", "*.hex"), ("所有文件", "*.*")])
        if filepath:
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, filepath)

    def _log(self, message):
        """向日志文本框追加一行消息"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.root.update_idletasks()

    def _on_merge(self):
        """合并按钮点击事件"""
        app_path = self.app_entry.get().strip()
        boot_path = self.boot_entry.get().strip()
        output_path = self.output_entry.get().strip()

        # 输入验证
        if not app_path:
            messagebox.showwarning("提示", "请选择 APP Hex 文件！")
            return
        if not boot_path:
            messagebox.showwarning("提示", "请选择 Boot Hex 文件！")
            return
        if not output_path:
            messagebox.showwarning("提示", "请指定输出文件路径！")
            return
        if not os.path.isfile(app_path):
            messagebox.showerror("错误", f"APP Hex 文件不存在：\n{app_path}")
            return
        if not os.path.isfile(boot_path):
            messagebox.showerror("错误", f"Boot Hex 文件不存在：\n{boot_path}")
            return

        # 禁用按钮，防止重复点击
        self.merge_btn.config(state=tk.DISABLED)
        self.clear_btn.config(state=tk.DISABLED)

        # 在后台线程执行合并，避免界面卡顿
        def run():
            try:
                process(app_path, boot_path, output_path,
                        log_callback=self._log)
                self.root.after(0, lambda: messagebox.showinfo(
                    "完成", f"合并完成！\n输出文件：{output_path}"))
            except Exception as e:
                self._log(f"\nERROR: {e}")
                self.root.after(0, lambda: messagebox.showerror(
                    "错误", f"合并失败：\n{e}"))
            finally:
                self.root.after(0, self._enable_buttons)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    def _enable_buttons(self):
        """重新启用按钮"""
        self.merge_btn.config(state=tk.NORMAL)
        self.clear_btn.config(state=tk.NORMAL)

    def _on_clear(self):
        """清除按钮点击事件"""
        self.app_entry.delete(0, tk.END)
        self.boot_entry.delete(0, tk.END)
        self.output_entry.delete(0, tk.END)
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)


def main():
    root = tk.Tk()
    HexMergeApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
