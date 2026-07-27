import tkinter as tk

root = tk.Tk()
text = tk.Text(root, wrap="word", font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4")
text.pack(fill="both", expand=True)

# Same tags as edm_agent.py
text.tag_configure("log_success", foreground="#22c55e", font=("Consolas", 9))
text.tag_configure("log_error",   foreground="#ef4444", font=("Consolas", 9))
text.tag_configure("step_save",   foreground="#ec4899", font=("Consolas", 9, "bold"))
text.tag_configure("msg_save",    foreground="#ec4899", font=("Consolas", 9))

# Insert using tag parameter (same as _gui_log_append)
text.insert("end", "✓ 绿色成功行\n", ("log_success",))
text.insert("end", "✗ 红色失败行\n", ("log_error",))
text.insert("end", "[10:30] ", ())
text.insert("end", "[保存]", ("step_save",))
text.insert("end", " 粉色消息文字\n", ("msg_save",))

# Verify tags exist
print("Tags configured:", text.tag_names())
root.update()

# Print what's actually in the widget
print("Widget text:", repr(text.get("1.0", "end")))
for tag in text.tag_names():
    ranges = text.tag_ranges(tag)
    print(f"Tag '{tag}' ranges: {ranges}")

root.after(3000, root.destroy)
root.mainloop()
