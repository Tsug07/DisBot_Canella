import customtkinter as ctk
from tkinter import messagebox
import subprocess
import os
import sys
import winreg
import json
from datetime import datetime
import threading
import pystray
from PIL import Image, ImageDraw

# Configurações do CustomTkinter
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class LogWindow(ctk.CTkToplevel):
    """Janela separada para mostrar logs"""
    def __init__(self, parent):
        super().__init__(parent)
        self.title("📋 Logs do Rebecca Bot")
        self.geometry("800x500")

        # Área de texto para logs
        self.log_text = ctk.CTkTextbox(self, width=780, height=440, font=("Consolas", 11))
        self.log_text.pack(padx=10, pady=10)

        # Botão limpar
        clear_btn = ctk.CTkButton(self, text="🗑️ Limpar Logs", command=self.clear_logs,
                                   fg_color="#e74c3c", hover_color="#c0392b")
        clear_btn.pack(pady=5)

        # Impede que feche completamente, apenas esconde
        self.protocol("WM_DELETE_WINDOW", self.withdraw)

    def add_log(self, message):
        """Adiciona log à janela"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")

    def clear_logs(self):
        """Limpa os logs"""
        self.log_text.delete("1.0", "end")
        self.add_log("Logs limpos")

class BotManager(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("🤖 Rebecca Bot Manager")
        self.geometry("500x520")
        self.resizable(False, False)

        self.bot_process = None
        self.is_running = False
        self.is_detached = False
        self.config_file = "bot_config.json"
        self.pid_file = "rebecca_bot.pid"

        # Janela de logs (oculta inicialmente)
        self.log_window = LogWindow(self)
        self.log_window.withdraw()

        self.load_config()
        self.setup_ui()
        self.check_autostart_status()
        self.check_detached_bot()
        self.create_tray_icon()  # Cria ícone na bandeja do sistema

        # Inicia o bot automaticamente se não estiver rodando
        if not self.is_running:
            self.after(1000, self.start_bot)  # Delay de 1 segundo para UI carregar

    def create_tray_icon(self):
        """Cria o ícone na bandeja do sistema"""

        # Desenha um ícone simples circular
        img = Image.new('RGB', (64, 64), color=(40, 40, 40))
        draw = ImageDraw.Draw(img)
        draw.ellipse((8, 8, 56, 56), fill=(0, 122, 255))

        menu = (
            pystray.MenuItem("Mostrar Gerenciador", self.show_window),
            pystray.MenuItem(
                "Parar Bot",
                self.stop_bot,
                enabled=lambda item: self.is_running
            ),
            pystray.MenuItem("Fechar Gerenciador", self.exit_from_tray)
        )

        self.tray_icon = pystray.Icon("RebeccaBot", img, "Rebecca Bot", menu)

        # Rodar em thread separada
        threading.Thread(target=self.tray_icon.run, daemon=True).start()
    
    def show_window(self, icon=None, item=None):
        self.after(0, self.deiconify)
        self.after(0, self.lift)

    def exit_from_tray(self, icon=None, item=None):
        if self.is_running:
            self.stop_bot()
        self.tray_icon.stop()
        self.destroy()


    def load_config(self):
        """Carrega configurações"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    self.config = json.load(f)
            else:
                self.config = {
                    "auto_restart": False,
                    "restart_interval_hours": 24,
                    "run_detached": True
                }
        except:
            self.config = {
                "auto_restart": False,
                "restart_interval_hours": 24,
                "run_detached": True
            }

    def save_config(self):
        """Salva configurações"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            self.log(f"Erro ao salvar: {str(e)}")

    def setup_ui(self):
        """Interface compacta e moderna"""
        # Título
        title = ctk.CTkLabel(self, text="🤖 Rebecca Bot Manager",
                            font=ctk.CTkFont(size=24, weight="bold"))
        title.pack(pady=20)

        # Status
        self.status_label = ctk.CTkLabel(self, text="● Desligado",
                                        font=ctk.CTkFont(size=16),
                                        text_color="#e74c3c")
        self.status_label.pack(pady=10)

        # Frame de botões principais
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=15)

        self.start_btn = ctk.CTkButton(btn_frame, text="▶️ Iniciar",
                                       command=self.start_bot,
                                       width=140, height=40,
                                       fg_color="#27ae60", hover_color="#229954")
        self.start_btn.grid(row=0, column=0, padx=5)

        self.stop_btn = ctk.CTkButton(btn_frame, text="⏹️ Parar",
                                      command=self.stop_bot,
                                      width=140, height=40,
                                      fg_color="#e74c3c", hover_color="#c0392b",
                                      state="disabled")
        self.stop_btn.grid(row=0, column=1, padx=5)

        self.restart_btn = ctk.CTkButton(btn_frame, text="🔄 Reiniciar",
                                        command=self.restart_bot,
                                        width=140, height=40,
                                        fg_color="#f39c12", hover_color="#e67e22",
                                        state="disabled")
        self.restart_btn.grid(row=0, column=2, padx=5)

        # Botão Ver Logs
        log_btn = ctk.CTkButton(self, text="📋 Ver Logs",
                               command=self.show_logs,
                               width=200, height=35,
                               fg_color="#3498db", hover_color="#2980b9")
        log_btn.pack(pady=10)

        # Configurações
        config_frame = ctk.CTkFrame(self)
        config_frame.pack(pady=15, padx=20, fill="x")

        config_title = ctk.CTkLabel(config_frame, text="⚙️ Configurações",
                                   font=ctk.CTkFont(size=14, weight="bold"))
        config_title.pack(pady=10)

        # Modo segundo plano
        self.detached_var = ctk.BooleanVar(value=self.config.get("run_detached", True))
        detached_switch = ctk.CTkSwitch(config_frame,
                                       text="🔒 Rodar em segundo plano",
                                       variable=self.detached_var,
                                       command=self.toggle_detached)
        detached_switch.pack(pady=5, padx=20, anchor="w")

        # Auto-iniciar
        self.autostart_var = ctk.BooleanVar()
        autostart_switch = ctk.CTkSwitch(config_frame,
                                        text="💻 Iniciar com Windows",
                                        variable=self.autostart_var,
                                        command=self.toggle_autostart)
        autostart_switch.pack(pady=5, padx=20, anchor="w")

        # Auto-restart
        restart_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
        restart_frame.pack(pady=5, padx=20, fill="x")

        self.auto_restart_var = ctk.BooleanVar(value=self.config.get("auto_restart", False))
        auto_restart_switch = ctk.CTkSwitch(restart_frame,
                                           text="🔄 Reiniciar a cada:",
                                           variable=self.auto_restart_var,
                                           command=self.toggle_auto_restart)
        auto_restart_switch.pack(side="left")

        self.interval_var = ctk.IntVar(value=self.config.get("restart_interval_hours", 24))
        interval_spin = ctk.CTkEntry(restart_frame, width=50,
                                    textvariable=self.interval_var)
        interval_spin.pack(side="left", padx=5)

        hours_label = ctk.CTkLabel(restart_frame, text="horas")
        hours_label.pack(side="left")

        # Info
        info_label = ctk.CTkLabel(self,
                                 text="✨ Bot em segundo plano continua rodando ao fechar",
                                 font=ctk.CTkFont(size=10),
                                 text_color="gray")
        info_label.pack(pady=10)

        # Log inicial
        self.log("Rebecca Bot Manager iniciado")
        self.log(f"Diretório: {os.getcwd()}")

    def log(self, message):
        """Adiciona mensagem ao log"""
        self.log_window.add_log(message)

    def show_logs(self):
        """Mostra janela de logs"""
        self.log_window.deiconify()
        self.log_window.lift()

    def check_detached_bot(self):
        """Verifica bot em segundo plano"""
        if os.path.exists(self.pid_file):
            try:
                with open(self.pid_file, 'r') as f:
                    pid = int(f.read().strip())

                try:
                    os.kill(pid, 0)
                    self.is_running = True
                    self.is_detached = True
                    self.update_status("Ligado (2º Plano)", "#27ae60")
                    self.start_btn.configure(state="disabled")
                    self.stop_btn.configure(state="normal")
                    self.restart_btn.configure(state="normal")
                    self.log(f"✅ Bot detectado em segundo plano (PID: {pid})")
                except (OSError, PermissionError):
                    os.remove(self.pid_file)
                    self.log("⚠️ Arquivo PID inválido removido")
            except:
                pass

    def start_bot(self):
        """Inicia o bot"""
        if self.is_running:
            self.log("⚠️ Bot já está rodando!")
            return

        try:
            self.log("🚀 Iniciando Rebecca Bot...")

            if sys.platform == 'win32':
                # Inicia o bot sem janela, mas mantendo os pipes para logs
                CREATE_NO_WINDOW = 0x08000000

                self.bot_process = subprocess.Popen(
                    [sys.executable, "-u", "rebecca_bot.py"],  # -u para unbuffered output
                    creationflags=CREATE_NO_WINDOW,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=0,  # Sem buffer
                    universal_newlines=True
                )
            else:
                self.bot_process = subprocess.Popen(
                    [sys.executable, "-u", "rebecca_bot.py"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=0,
                    universal_newlines=True,
                    start_new_session=True
                )

            # Salva PID
            with open(self.pid_file, 'w') as f:
                f.write(str(self.bot_process.pid))

            self.is_running = True
            self.is_detached = True
            self.update_status("Ligado", "#27ae60")
            self.start_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")
            self.restart_btn.configure(state="normal")

            self.log(f"✅ Bot iniciado em segundo plano (PID: {self.bot_process.pid})")
            self.log("   Clique em 'Ver Logs' para acompanhar a atividade do bot!")

            # Inicia thread para ler logs do bot
            threading.Thread(target=self.read_bot_logs, daemon=True).start()

            if self.auto_restart_var.get():
                self.schedule_auto_restart()

        except Exception as e:
            self.log(f"❌ Erro: {str(e)}")
            self.update_status("Erro", "#e74c3c")

    def read_bot_logs(self):
        """Lê os logs do bot em tempo real"""
        import queue
        import time

        def enqueue_output(pipe, queue_obj, prefix):
            """Função auxiliar para ler pipe em thread separada"""
            try:
                for line in iter(pipe.readline, ''):
                    if line:
                        queue_obj.put((prefix, line))
                pipe.close()
            except:
                pass

        try:
            # Cria filas para stdout e stderr
            out_queue = queue.Queue()
            err_queue = queue.Queue()

            # Threads para ler stdout e stderr de forma não-bloqueante
            out_thread = threading.Thread(
                target=enqueue_output,
                args=(self.bot_process.stdout, out_queue, "stdout"),
                daemon=True
            )
            err_thread = threading.Thread(
                target=enqueue_output,
                args=(self.bot_process.stderr, err_queue, "stderr"),
                daemon=True
            )

            out_thread.start()
            err_thread.start()

            while self.is_running and self.bot_process:
                # Lê da fila de stdout
                try:
                    while True:
                        _, line = out_queue.get_nowait()
                        if line and line.strip():
                            self.log(f"[BOT] {line.strip()}")
                except queue.Empty:
                    pass

                # Lê da fila de stderr
                try:
                    while True:
                        _, line = err_queue.get_nowait()
                        if line and line.strip():
                            line_lower = line.lower()
                            if 'error' in line_lower or 'exception' in line_lower or 'traceback' in line_lower:
                                self.log(f"❌ [BOT ERROR] {line.strip()}")
                            else:
                                self.log(f"[BOT] {line.strip()}")
                except queue.Empty:
                    pass

                # Verifica se o processo ainda está rodando
                if self.bot_process.poll() is not None:
                    # Lê qualquer log restante
                    time.sleep(0.5)
                    while not out_queue.empty():
                        _, line = out_queue.get_nowait()
                        if line and line.strip():
                            self.log(f"[BOT] {line.strip()}")
                    while not err_queue.empty():
                        _, line = err_queue.get_nowait()
                        if line and line.strip():
                            self.log(f"[BOT] {line.strip()}")

                    self.log("⚠️ Bot parou!")
                    self.is_running = False
                    self.is_detached = False
                    self.after(0, lambda: self.update_status("Desligado", "#e74c3c"))
                    self.after(0, lambda: self.start_btn.configure(state="normal"))
                    self.after(0, lambda: self.stop_btn.configure(state="disabled"))
                    self.after(0, lambda: self.restart_btn.configure(state="disabled"))

                    if os.path.exists(self.pid_file):
                        os.remove(self.pid_file)
                    break

                time.sleep(0.1)  # Pequeno delay para não sobrecarregar CPU

        except Exception as e:
            self.log(f"❌ Erro ao ler logs: {str(e)}")

    def stop_bot(self):
        """Para o bot"""
        if not self.is_running:
            self.log("⚠️ Bot não está rodando!")
            return

        try:
            self.log("🛑 Parando bot...")

            if os.path.exists(self.pid_file):
                with open(self.pid_file, 'r') as f:
                    pid = int(f.read().strip())

                try:
                    if sys.platform == 'win32':
                        import ctypes
                        kernel = ctypes.windll.kernel32
                        handle = kernel.OpenProcess(1, False, pid)
                        kernel.TerminateProcess(handle, 0)
                        kernel.CloseHandle(handle)
                    else:
                        import signal
                        os.kill(pid, signal.SIGTERM)

                    os.remove(self.pid_file)
                    self.log(f"✅ Bot parado (PID: {pid})")
                except ProcessLookupError:
                    self.log("⚠️ Processo já foi encerrado")
                    os.remove(self.pid_file)

            self.is_running = False
            self.is_detached = False
            self.update_status("Desligado", "#e74c3c")
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")
            self.restart_btn.configure(state="disabled")

        except Exception as e:
            self.log(f"❌ Erro ao parar: {str(e)}")

    def restart_bot(self):
        """Reinicia o bot"""
        self.log("🔄 Reiniciando...")
        self.stop_bot()
        self.after(2000, self.start_bot)

    def schedule_auto_restart(self):
        """Agenda restart automático"""
        if self.auto_restart_var.get() and self.is_running:
            interval_ms = self.interval_var.get() * 60 * 60 * 1000
            self.log(f"⏰ Próximo restart em {self.interval_var.get()}h")
            self.after(interval_ms, self.auto_restart)

    def auto_restart(self):
        """Executa restart automático"""
        if self.auto_restart_var.get() and self.is_running:
            self.log("⏰ Restart automático programado")
            self.restart_bot()

    def toggle_detached(self):
        """Toggle segundo plano"""
        self.config["run_detached"] = self.detached_var.get()
        self.save_config()
        status = "ATIVADO" if self.detached_var.get() else "DESATIVADO"
        self.log(f"🔒 Segundo plano: {status}")

    def toggle_auto_restart(self):
        """Toggle auto-restart"""
        self.config["auto_restart"] = self.auto_restart_var.get()
        self.config["restart_interval_hours"] = self.interval_var.get()
        self.save_config()

        if self.auto_restart_var.get():
            self.log(f"✅ Auto-restart: a cada {self.interval_var.get()}h")
            if self.is_running:
                self.schedule_auto_restart()
        else:
            self.log("❌ Auto-restart desativado")

    def update_status(self, text, color):
        """Atualiza status visual"""
        self.status_label.configure(text=f"● {text}", text_color=color)

    def check_autostart_status(self):
        """Verifica autostart"""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Run",
                                0, winreg.KEY_READ)
            try:
                winreg.QueryValueEx(key, "RebeccaBot")
                self.autostart_var.set(True)
            except FileNotFoundError:
                self.autostart_var.set(False)
            finally:
                winreg.CloseKey(key)
        except:
            self.autostart_var.set(False)

    def toggle_autostart(self):
        """Toggle autostart Windows"""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Run",
                                0, winreg.KEY_SET_VALUE)

            if self.autostart_var.get():
                script_path = os.path.abspath("rebecca_bot.py")
                python_path = sys.executable
                pythonw_path = python_path.replace("python.exe", "pythonw.exe")

                if os.path.exists(pythonw_path):
                    command = f'"{pythonw_path}" "{script_path}"'
                else:
                    command = f'"{python_path}" "{script_path}"'

                winreg.SetValueEx(key, "RebeccaBot", 0, winreg.REG_SZ, command)
                self.log("✅ Autostart: ATIVADO")
            else:
                try:
                    winreg.DeleteValue(key, "RebeccaBot")
                    self.log("❌ Autostart: DESATIVADO")
                except FileNotFoundError:
                    pass

            winreg.CloseKey(key)

        except Exception as e:
            self.log(f"❌ Erro autostart: {str(e)}")
            messagebox.showerror("Erro", f"Erro ao configurar autostart:\n{str(e)}")

    def on_closing(self):
        """Ao fechar, envia para bandeja se o bot estiver rodando"""
        if self.is_running:
            self.withdraw()  # esconde a janela
            self.log("ℹ️ Gerenciador ocultado na bandeja.")
        else:
            self.tray_icon.stop()
            self.destroy()

def main():
    app = BotManager()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()

if __name__ == "__main__":
    main()
