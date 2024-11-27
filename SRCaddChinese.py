#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
字幕中文翻译工具

本工具用于将英文字幕文件翻译成中文，并生成双语字幕。

主要功能:
1. 支持批量导入SRT格式字幕文件
2. 使用Google翻译API进行中文翻译
3. 保持原字幕时间轴不变
4. 生成双语字幕文件
5. 支持进度显示和错误处理
6. 使用多线程避免界面卡顿

作者:fristyy
创建日期: 2023-11
"""


import sys
import os
import time
from PyQt5.QtWidgets import (QApplication, QMainWindow, QPushButton, QTextEdit, 
                           QVBoxLayout, QHBoxLayout, QWidget, QFileDialog, QLabel,
                           QProgressDialog, QMessageBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from googletrans import Translator
import httpcore

class SrtFile:
    """
    SRT字幕文件处理类
    
    用于读取、解析和处理SRT格式的字幕文件。
    
    属性:
        filename (str): 字幕文件路径
        entries (list): 存储字幕条目的列表,每个条目包含:
            - index: 字幕序号
            - time: 时间轴信息
            - text: 字幕文内容
    
    方法:
        parse(): 解析SRT文件内容
        save(filename): 保存字幕到新文件
        get_texts(): 获取所有字幕文本
        update_texts(texts): 更新字幕文本
    """

class TranslatorThread(QThread):
    """
    翻译线程类
    
    用于在后台执行字幕翻译任务,避免界面卡顿。
    
    信号:
        finished: 翻译完成时发出,携带翻译结果列表
        error: 发生错误时发出,携带错误信息
        progress: 翻译进度更新时发出,携带进度值(0-100)
        translation_started: 翻译开始时发出
    """
    finished = pyqtSignal(list)  # 翻译完成信号
    error = pyqtSignal(str)      # 错误信号
    progress = pyqtSignal(int)   # 进度信号
    translation_started = pyqtSignal()  # 翻译开始信号

    def __init__(self, texts, parent=None):
        super().__init__(parent)
        self.texts = texts
        self.translator = None
        
    def test_proxy(self):
        """测试代理连接"""
        try:
            # 设置代理环境变量
            os.environ['http_proxy'] = 'http://127.0.0.1:7890'
            os.environ['https_proxy'] = 'http://127.0.0.1:7890'
            
            import requests
            # 测试连接Google翻译
            response = requests.get('http://translate.google.com', timeout=5)
            if response.status_code == 200:
                # 创建翻译器
                self.translator = Translator(service_urls=['translate.google.com'])
                return True
            return False
        except Exception as e:
            raise Exception(f"代理连接测试失败: {str(e)}")

    def run(self):
        """执行翻译任务"""
        try:
            # 首先测试代理连接
            if not self.test_proxy():
                return
                
            translated_texts = []
            total = len(self.texts)
            
            # 发出翻译开始信号
            self.translation_started.emit()
            
            for i, text in enumerate(self.texts):
                if text.strip():  # 只翻译非空文本
                    translated = self.translate_text(text)
                    translated_texts.append(translated)
                else:
                    translated_texts.append("")
                    
                # 更新进度
                progress = int((i + 1) / total * 100)
                self.progress.emit(progress)
                
                # 避免请求过快
                time.sleep(0.5)
                
            self.finished.emit(translated_texts)
            
        except Exception as e:
            self.error.emit(str(e))
        finally:
            # 清除代理环境变量
            if 'http_proxy' in os.environ:
                del os.environ['http_proxy']
            if 'https_proxy' in os.environ:
                del os.environ['https_proxy']

    def translate_text(self, text):
        """翻译单条文本"""
        try:
            # 尝试最多3次翻译
            for _ in range(3):
                try:
                    result = self.translator.translate(text, dest='zh-cn')
                    return result.text
                except Exception as e:
                    time.sleep(1)  # 失败后等待1秒再试
                    continue
            raise Exception("翻译重试次数超过限制")
        except Exception as e:
            raise Exception(f"翻译失败: {str(e)}")

class SubtitleEditor(QMainWindow):
    """
    字幕编辑器主窗口类
    
    用于创建和管理字幕编辑器的主界面，处理用户交互和字幕翻译功能。
    
    属性:
        current_file (str): 当前打开的字幕文件路径
        is_translating (bool): 标记是否正在进行翻译
        progress_dialog: 翻译进度对话框实例
    """
    
    def __init__(self):
        super().__init__()
        self.initUI()
        self.current_file = None
        self.is_translating = False
        self.progress_dialog = None
        
    def initUI(self):
        """
        初始化用户界面
        
        创建并设置所有UI组件，包括按钮、文本框和布局。
        设置窗口属性和初始状态。
        """
        
        # 创建主窗口部件和布局
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        
        # 文件选择区域
        file_layout = QHBoxLayout()
        self.file_label = QLabel('当前文件：未选择')
        self.select_file_btn = QPushButton('选择字幕文件')
        self.select_file_btn.clicked.connect(self.selectFile)
        file_layout.addWidget(self.file_label)
        file_layout.addWidget(self.select_file_btn)
        
        # 添加翻译按钮
        self.translate_btn = QPushButton('添加中文字幕')
        self.translate_btn.clicked.connect(self.addTranslation)
        self.translate_btn.setEnabled(False)
        
        # 文本编辑区域
        self.text_edit = QTextEdit()
        
        # 保存按钮布局
        save_layout = QHBoxLayout()
        
        # 保存双语字幕按钮
        self.save_btn = QPushButton('保存双语字幕')
        self.save_btn.clicked.connect(self.saveFile)
        self.save_btn.setEnabled(False)
        
        # 保存中文字幕按钮
        self.save_chinese_btn = QPushButton('保存中文字幕')
        self.save_chinese_btn.clicked.connect(self.saveChineseOnly)
        self.save_chinese_btn.setEnabled(False)
        
        save_layout.addWidget(self.save_btn)
        save_layout.addWidget(self.save_chinese_btn)
        
        # 将所有部件添加到主布局
        layout.addLayout(file_layout)
        layout.addWidget(self.translate_btn)
        layout.addWidget(self.text_edit)
        layout.addLayout(save_layout)
        
        # 设置窗口属性
        self.setGeometry(300, 300, 800, 600)
        self.setWindowTitle('字幕翻译编辑器')
        
    def createProgressDialog(self):
        """
        创建进度对话框
        
        初始化用于显示翻译进度的对话框，设置其属性和行为。
        """
        
        # 建进度对话框
        self.progress_dialog = QProgressDialog("正在翻译中...", "取消", 0, 100, self)
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setAutoClose(True)
        self.progress_dialog.setAutoReset(True)
        self.progress_dialog.canceled.connect(self.cancelTranslation)
        
    def showProgress(self):
        """
        显示进度对话框
        
        在需要时创建并显示进度对话框，用于展示翻译进度。
        """
        
        # 确保进度对话框存在
        if not self.progress_dialog:
            self.createProgressDialog()
        # 显示进度对话框
        self.progress_dialog.setValue(0)
        self.progress_dialog.show()
    
    def selectFile(self):
        """
        选择字幕文件
        
        打开文件选择对话框，让用户选择要处理的字幕文件。
        读取选中的文件内容并显示在编辑器中。
        
        错误处理:
            - 文件读取失败时显示错误信息
            - 更新相关按钮的启用状态
        """
        
        fname, _ = QFileDialog.getOpenFileName(self, '选择字幕文件', '', 
                                             'Subtitle files (*.srt);;All files (*.*)')
        if fname:
            self.current_file = fname
            self.file_label.setText(f'当前文件：{fname}')
            
            try:
                with open(fname, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.text_edit.setText(content)
                self.translate_btn.setEnabled(True)
                self.save_btn.setEnabled(True)
                self.save_chinese_btn.setEnabled(True)
            except Exception as e:
                self.text_edit.setText(f'错误：无法读取文件\n{str(e)}')
                self.translate_btn.setEnabled(False)
                self.save_btn.setEnabled(False)
                self.save_chinese_btn.setEnabled(False)
    
    def process_subtitle_lines(self, lines, process_type='translate'):
        """
        处理字幕行的通用函数
        
        参数:
            lines (list): 字幕文件的所有行
            process_type (str): 处理类型
                - 'translate': 提取需要翻译的文本
                - 'chinese_only': 只提取中文字幕
                
        返回:
            如果是translate类型，返回需要翻译的文本列表
            如果是chinese_only类型，返回只包含中文的字幕行列表
        """
        result = []
        i = 0
        subtitle_count = 1

        while i < len(lines):
            line = lines[i].strip()
            if line.isdigit():  # 字幕序号
                if process_type == 'translate':
                    i += 2  # 跳过时间码
                    if i < len(lines):
                        result.append(lines[i].strip())
                else:  # chinese_only
                    result.append(str(subtitle_count))  # 添加新序号
                    i += 1
                    if i < len(lines):
                        result.append(lines[i])  # 添加时间码
                        i += 2  # 跳过英文字幕
                        if i < len(lines) and not lines[i].strip().isdigit():
                            result.append(lines[i])  # 添加中文字幕
                            subtitle_count += 1
            i += 1
        
        return result

    def addTranslation(self):
        """添加中文翻译"""
        if not self.current_file or self.is_translating:
            return
            
        self.is_translating = True
        self.translate_btn.setEnabled(False)
        self.select_file_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.save_chinese_btn.setEnabled(False)
        
        content = self.text_edit.toPlainText()
        lines = content.split('\n')
        
        # 使用通用函数提取需要翻译的文本
        texts_to_translate = self.process_subtitle_lines(lines, 'translate')
            
        # 创建并启动翻译线程
        self.translator_thread = TranslatorThread(texts_to_translate)
        self.translator_thread.finished.connect(self.onTranslationFinished)
        self.translator_thread.error.connect(self.onTranslationError)
        self.translator_thread.progress.connect(self.updateProgress)
        self.translator_thread.translation_started.connect(self.showProgress)
        
        # 开始翻译
        self.translator_thread.start()

    def cancelTranslation(self):
        """
        取消翻译
        
        中断正在进行的翻译过程：
        1. 终止翻译线程
        2. 重置翻译状态
        3. 恢复按钮可用性
        """
        
        if hasattr(self, 'translator_thread'):
            self.translator_thread.terminate()
            self.is_translating = False
            self.translate_btn.setEnabled(True)
            self.select_file_btn.setEnabled(True)
            self.save_btn.setEnabled(True)
            self.save_chinese_btn.setEnabled(True)
    
    def onTranslationFinished(self, translated_texts):
        """
        翻译完成处理
        
        处理翻译完成后的操作：
        1. 将翻译结果添加到原文本中
        2. 更新界面显示
        3. 恢复按钮状态
        
        参数:
            translated_texts (list): 翻译完成的文本列表
        """
        
        content = self.text_edit.toPlainText()
        lines = content.split('\n')
        new_lines = []
        trans_index = 0
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            new_lines.append(lines[i])  # 添加原行
            
            if line.isdigit():  # 字幕序号
                i += 2  # 跳过时间码
                new_lines.append(lines[i-1])  # 添加时间码
                if i < len(lines):
                    new_lines.append(lines[i])  # 添加英文
                    if trans_index < len(translated_texts):
                        new_lines.append(translated_texts[trans_index])  # 添加翻译
                        trans_index += 1
            i += 1
            
        self.text_edit.setText('\n'.join(new_lines))
        self.progress_dialog.hide()
        self.is_translating = False
        self.translate_btn.setEnabled(True)
        self.select_file_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        self.save_chinese_btn.setEnabled(True)
        
    def onTranslationError(self, error_msg):
        """
        翻译错误处理
        
        处理翻译过程中的错误：
        1. 隐藏进度对话框
        2. 显示错误消息
        3. 恢复界面状态
        
        参数:
            error_msg (str): 错误信息
        """
        
        self.progress_dialog.hide()
        self.is_translating = False
        self.translate_btn.setEnabled(True)
        self.select_file_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        self.save_chinese_btn.setEnabled(True)
        QMessageBox.critical(self, "翻译错误", error_msg)
        
    def updateProgress(self, value):
        """
        更新进度显示
        
        更新进度对话框的进度值
        
        参数:
            value (int): 当前进度值(0-100)
        """
        
        self.progress_dialog.setValue(value)
    
    def saveFile(self):
        """
        保存双语字幕文件
        
        将当前编辑器中的内容保存为新的字幕文件：
        1. 使用原文件名添加"_中文"后缀
        2. 保存为UTF-8编码的文件
        
        错误处理:
            - 保存失败时显示错误消息
        """
        
        if not self.current_file:
            return
            
        file_path = self.current_file
        new_file_path = file_path.rsplit('.', 1)[0] + '_中文.srt'
        
        try:
            with open(new_file_path, 'w', encoding='utf-8') as f:
                f.write(self.text_edit.toPlainText())
            self.file_label.setText(f'文件已保存：{new_file_path}')
        except Exception as e:
            QMessageBox.critical(self, "保存错误", f"无法保存文件：{str(e)}")
    
    def saveChineseOnly(self):
        """保存仅中文字幕文件"""
        if not self.current_file:
            return
            
        file_path = self.current_file
        new_file_path = file_path.rsplit('.', 1)[0] + '_仅中文.srt'
        
        try:
            content = self.text_edit.toPlainText()
            lines = content.split('\n')
            
            # 使用通用函数提取中文字幕
            chinese_lines = self.process_subtitle_lines(lines, 'chinese_only')
            
            # 保存文件
            with open(new_file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(chinese_lines))
            self.file_label.setText(f'文件已保存：{new_file_path}')
            QMessageBox.information(self, "保存成功", f"中文字幕已保存至：{new_file_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "保存错误", f"无法保存文件：{str(e)}")

def main():
    """
    程序入口函数
    
    创建并运行字幕编辑器应用：
    1. 初始化QT应用程序
    2. 创建主窗口实例
    3. 显示界面并进入事件循环
    """
    
    app = QApplication(sys.argv)
    ex = SubtitleEditor()
    ex.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()