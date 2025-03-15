import re
import queue
import threading
import tkinter as tk
from tkinter import messagebox
import ollama

# 定义常量
BOARD_SIZE = 15
GRID_SIZE = 40
WINDOW_WIDTH = GRID_SIZE * (BOARD_SIZE + 1)
WINDOW_HEIGHT = GRID_SIZE * (BOARD_SIZE + 1)
BLACK_PLAYER = 1
WHITE_PLAYER = 2
MAX_RETRIES = 2
STEP_INTERVAL = 100
# 新增颜色常量
BOARD_BACKGROUND_COLOR = "#CC9966"
COORDINATE_TEXT_COLOR = "black"
PREVIEW_RECT_OUTLINE_COLOR = "red"
MODEL1_TEXT_COLOR = "blue"
MODEL2_TEXT_COLOR = "green"
ERROR_TEXT_COLOR = "red"
STEP_TEXT_COLOR = "orange"
BLACK_PIECE_COLOR = "black"
WHITE_PIECE_COLOR = "white"

MODEL_1 = "qwen2.5:latest"
MODEL_2 = "deepseek-r1:8b"

class GomokuGame:
    def __init__(self, root):
        """
        初始化五子棋游戏。

        :param root: Tkinter 根窗口
        """
        self.root = root
        self.root.title("五子棋游戏")
        self.root.resizable(False, False)

        # 初始化得分
        self.black_score = 0
        self.white_score = 0

        # 初始化记分牌
        self.score_board = tk.Label(self.root, text=f"黑棋: {self.black_score}  白棋: {self.white_score}",
                                    font=("simhei", 16), anchor="center", height=1)
        self.score_board.grid(row=0, column=1, sticky="nsew", padx=1, pady=1)
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)

        # 创建左侧的画布用于绘制棋盘
        self.canvas = tk.Canvas(self.root, width=WINDOW_WIDTH, height=WINDOW_HEIGHT)
        self.canvas.grid(row=0, column=0, rowspan=2, sticky="nsew")
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # 创建右侧的文本框
        self.text_frame = tk.Frame(self.root)
        self.text_frame.grid(row=1, column=1, sticky="nsew")
        self.root.grid_rowconfigure(1, weight=9)
        self.root.grid_columnconfigure(1, weight=1)
        self.text_frame.grid_columnconfigure(0, weight=1)
        self.text_frame.grid_rowconfigure(0, weight=1)

        # 创建垂直滚动条
        self.scrollbar = tk.Scrollbar(self.text_frame, orient=tk.VERTICAL)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.text_box = tk.Text(self.text_frame, yscrollcommand=self.scrollbar.set)
        self.text_box.pack(fill=tk.BOTH, expand=True)

        # 将滚动条与文本框关联
        self.scrollbar.config(command=self.text_box.yview)
        # 为两个模型配置不同的颜色标签
        self.text_box.tag_config("model1", foreground=MODEL1_TEXT_COLOR)
        self.text_box.tag_config("model2", foreground=MODEL2_TEXT_COLOR)
        self.text_box.tag_config("error", foreground=ERROR_TEXT_COLOR)
        self.text_box.tag_config("step", foreground=STEP_TEXT_COLOR)

        # 预点击虚框的ID
        self.preview_rect = None

        # 初始化棋盘状态
        self.board = [[0] * BOARD_SIZE for _ in range(BOARD_SIZE)]

        # 当前玩家，1 表示黑棋，2 表示白棋
        self.current_player = 1

        # 模型列表
        self.models = [MODEL_1, MODEL_2]

        # 用于线程间通信的队列
        self.result_queue = queue.Queue()

        # 新增步数计数器
        self.step_count = 0
        # 定义步数文本颜色
        self.STEP_TEXT_COLOR_BLACK = STEP_TEXT_COLOR
        self.STEP_TEXT_COLOR_WHITE = STEP_TEXT_COLOR

        # 绘制棋盘
        self.draw_board()

        # 绑定鼠标事件
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<Button-1>", self.on_click)

        # 开始游戏，让第一个模型先落子
        self.model_move()

    def draw_board(self):
        """
        绘制五子棋棋盘。
        """
        self.canvas.configure(bg=BOARD_BACKGROUND_COLOR)
        for i in range(BOARD_SIZE):
            self.canvas.create_line(GRID_SIZE, GRID_SIZE * (i + 1),
                                    GRID_SIZE * BOARD_SIZE, GRID_SIZE * (i + 1), width=2)
            self.canvas.create_line(GRID_SIZE * (i + 1), GRID_SIZE,
                                    GRID_SIZE * (i + 1), GRID_SIZE * BOARD_SIZE, width=2)

        # 绘制数字坐标
        for i in range(BOARD_SIZE):
            # 顶部坐标
            self.canvas.create_text(GRID_SIZE * (i + 1), GRID_SIZE // 2, text=str(i + 1), fill=COORDINATE_TEXT_COLOR)
            # 左侧坐标
            self.canvas.create_text(GRID_SIZE // 2, GRID_SIZE * (i + 1), text=str(i + 1), fill=COORDINATE_TEXT_COLOR)

    def get_move_from_model(self, model_name, board_state):
        """
        从模型获取落子位置。
    
        :param model_name: 模型名称
        :param board_state: 当前棋盘状态
        :return: 落子的行和列，错误信息，思考结果
        """
        # 将棋盘状态转换为字符串
        board_str = "\n".join([" ".join(map(str, row)) for row in board_state])
        # 修改提示词，添加棋盘大小信息
        prompt = f"""
                你是一名五子棋高手，你需要尽可能完成五子连珠，
                当前棋盘大小为 {BOARD_SIZE}x{BOARD_SIZE}，横纵坐标均为1-{BOARD_SIZE}，
                当前棋盘状态以二维数组形式表示，其中每个元素代表棋盘上的一个格子，0 表示该格子为空，1表示黑棋，2表示白棋。
                棋盘状态:\n{board_str}\n，
                落子位置必须是棋盘上的空位置（即对应元素为 0）；
                当前你执 {'黑棋' if self.current_player == 1 else '白棋'}，
                请给出落子的行和列，格式：(3,5)
            """
        retries = 0
        while retries < MAX_RETRIES:
            try:
                result = ollama.generate(model_name, prompt)
                result_text = result["response"].strip()
                pattern = r'[（(](\d+)\s*[,，]\s*(\d+)[）)]'
                match = re.findall(pattern, result_text)
                if match:
                    row, col = map(int, match[-1])
                    # 检查坐标合法性
                    if 1 <= row <= BOARD_SIZE and 1 <= col <= BOARD_SIZE and board_state[row - 1][col - 1] == 0:
                        return row - 1, col - 1, None, result_text  # 返回思考结果
                    else:
                        self._handle_invalid_move(model_name, retries, result_text, row, col)  # 传递 row 和 col
                else:
                    self._handle_no_coordinates(model_name, retries, result_text)  # 传递思考结果
            except Exception as e:
                # 将错误信息显示在文本框中
                self.text_box.insert(tk.END, f"【{model_name}】 出现错误: {e}，重试第 {retries + 1} 次...\n")
            retries += 1
        return None, None, f"【{model_name}】 重试 {MAX_RETRIES} 次后仍无法获取有效坐标", None

    def _handle_invalid_move(self, model_name, retries, result_text, row, col):
        """
        处理模型返回的非法落子位置。
    
        :param model_name: 模型名称
        :param retries: 重试次数
        :param result_text: 模型思考结果
        :param row: 落子的行
        :param col: 落子的列
        """
        tag = "model1" if (self.current_player - 1) % 2 == 0 else "model2"
        # 显示非法落子的具体位置
        self.text_box.insert(tk.END, f"【{model_name}】 思考结果: {result_text}\n", tag)  # 显示思考结果
        self.text_box.insert(tk.END, f"【{model_name}】 返回非法坐标 ({row}, {col})，重试第 {retries + 1} 次...\n", (ERROR_TEXT_COLOR,))

        # 非法落子扣1分
        if self.current_player == BLACK_PLAYER:
            self.black_score -= 1
        else:
            self.white_score -= 1
        # 更新记分牌显示
        self.score_board.config(text=f"黑棋: {self.black_score}  白棋: {self.white_score}")

    def _handle_no_coordinates(self, model_name, retries, result_text):
        """
        处理模型无法截取坐标值的情况。
    
        :param model_name: 模型名称
        :param retries: 重试次数
        :param result_text: 模型思考结果
        """
        tag = "model1" if (self.current_player - 1) % 2 == 0 else "model2"
        self.text_box.insert(tk.END, f"【{model_name}】 思考结果: {result_text}\n", tag)  # 显示思考结果
        self.text_box.insert(tk.END, f"【{model_name}】 无法截取坐标值，重试第 {retries + 1} 次...\n", (ERROR_TEXT_COLOR,))

    def on_motion(self, event):
        """
        处理鼠标移动事件。

        :param event: 鼠标事件
        """
        x, y = event.x, event.y
        if GRID_SIZE <= x <= GRID_SIZE * (BOARD_SIZE + 1) and GRID_SIZE <= y <= GRID_SIZE * (BOARD_SIZE + 1):
            col = (x - GRID_SIZE) // GRID_SIZE
            row = (y - GRID_SIZE) // GRID_SIZE
            # 删除之前的虚框
            if self.preview_rect:
                self.canvas.delete(self.preview_rect)
            # 绘制新的虚框
            self.preview_rect = self.canvas.create_rectangle(
                GRID_SIZE * (col + 1) - 18, GRID_SIZE * (row + 1) - 18,
                GRID_SIZE * (col + 1) + 18, GRID_SIZE * (row + 1) + 18,
                outline="red", dash=(4, 4)
            )
        else:
            # 如果鼠标移出棋盘区域，删除虚框
            if self.preview_rect:
                self.canvas.delete(self.preview_rect)
                self.preview_rect = None

    def check_win(self, board, player):
        """
        检查玩家是否获胜。

        :param board: 当前棋盘状态
        :param player: 玩家编号
        :return: 是否获胜
        """
        directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
        for i in range(BOARD_SIZE):
            for j in range(BOARD_SIZE):
                if board[i][j] == player:
                    for dx, dy in directions:
                        count = 1
                        # 正向检查
                        for k in range(1, 5):
                            ni, nj = i + k * dx, j + k * dy
                            if 0 <= ni < BOARD_SIZE and 0 <= nj < BOARD_SIZE and board[ni][nj] == player:
                                count += 1
                            else:
                                break
                        # 反向检查
                        for k in range(1, 5):
                            ni, nj = i - k * dx, j - k * dy
                            if 0 <= ni < BOARD_SIZE and 0 <= nj < BOARD_SIZE and board[ni][nj] == player:
                                count += 1
                            else:
                                break
                        if count >= 5:
                            return True
        return False

    def get_player_color(self, player):
        """
        获取玩家的颜色名称。

        :param player: 玩家编号
        :return: 玩家的颜色名称
        """
        return "黑" if player == BLACK_PLAYER else "白"

    def get_fill_color(self, player):
        """
        获取玩家棋子的填充颜色。

        :param player: 玩家编号
        :return: 玩家棋子的填充颜色
        """
        return "black" if player == BLACK_PLAYER else "white"

    def on_click(self, event):
        """
        处理鼠标点击事件。

        :param event: 鼠标事件
        """
        x, y = event.x, event.y
        if GRID_SIZE <= x <= GRID_SIZE * (BOARD_SIZE + 1) and GRID_SIZE <= y <= GRID_SIZE * (BOARD_SIZE + 1):
            col = (x - GRID_SIZE) // GRID_SIZE
            row = (y - GRID_SIZE) // GRID_SIZE
            if self.board[row][col] == 0:
                color = self.get_player_color(self.current_player)
                fill_color = self.get_fill_color(self.current_player)
                self.canvas.create_oval(GRID_SIZE * (col + 1) - 18, GRID_SIZE * (row + 1) - 18,
                                        GRID_SIZE * (col + 1) + 18, GRID_SIZE * (row + 1) + 18,
                                        fill=fill_color)
                self.board[row][col] = self.current_player
                self.step_count += 1  # 增加步数
                # 根据当前玩家选择步数文本颜色
                step_color = self.STEP_TEXT_COLOR_BLACK if self.current_player == BLACK_PLAYER else self.STEP_TEXT_COLOR_WHITE
                self.canvas.create_text(GRID_SIZE * (col + 1), GRID_SIZE * (row + 1),
                                        text=str(self.step_count),
                                        fill=step_color)  # 修改颜色为规定的颜色
                #print(f"绘制步数文字: 坐标 ({GRID_SIZE * (col + 1)}, {GRID_SIZE * (row + 1)}), 步数 {self.step_count}")  # 添加调试信息
                # 在右侧消息栏显示信息，包含步数，应用 'step' 标签
                self.text_box.insert(tk.END, f"用户在第 {row + 1} 行，第 {col + 1} 列落子（{color}），步数: {self.step_count}\n", ("step",))
                # 删除虚框
                if self.preview_rect:
                    self.canvas.delete(self.preview_rect)
                    self.preview_rect = None
                # 检查是否获胜
                if self.check_win(self.board, self.current_player):
                    self.show_win_message(self.current_player)
                    return
                # 切换玩家
                self.current_player = WHITE_PLAYER if self.current_player == BLACK_PLAYER else BLACK_PLAYER
                # 调用模型进行落子
                self.model_move()

    def process_result_queue(self):
        """
        处理队列中的结果。
        """
        try:
            row, col, error, result, model_name, color, tag = self.result_queue.get_nowait()
            if result:
                self.text_box.insert(tk.END, f"【{model_name}】 思考结果: {result}\n", tag)
            if row is not None and col is not None and self.board[row][col] == 0:
                self.step_count += 1
                # 根据当前玩家选择步数文本颜色
                step_color = self.STEP_TEXT_COLOR_BLACK if self.current_player == BLACK_PLAYER else self.STEP_TEXT_COLOR_WHITE
                # 先绘制棋子
                self.canvas.create_oval(GRID_SIZE * (col + 1) - 18, GRID_SIZE * (row + 1) - 18,
                                        GRID_SIZE * (col + 1) + 18, GRID_SIZE * (row + 1) + 18,
                                        fill=self.get_fill_color(self.current_player))
                # 再绘制步数文字
                self.canvas.create_text(GRID_SIZE * (col + 1), GRID_SIZE * (row + 1),
                                        text=str(self.step_count),
                                        fill=step_color)  # 修改颜色为规定的颜色
                # 在右侧消息栏显示信息，包含步数
                self.text_box.insert(tk.END, f"【{model_name}】在第 {row + 1} 行，第 {col + 1} 列落子（{color}），步数: {self.step_count}\n", ("step",))
                # 直接更新棋盘状态
                self.board[row][col] = self.current_player
                # 检查是否获胜
                if self.check_win(self.board, self.current_player):
                    self.show_win_message(self.current_player)
                    return
                # 切换玩家
                self.current_player = WHITE_PLAYER if self.current_player == BLACK_PLAYER else BLACK_PLAYER
                self.model_move()
            else:
                if error == "无法截取坐标值":
                    self.text_box.insert(tk.END, f"无法截取【{model_name}】 的坐标值，请用户操作\n", tag)
                else:
                    self.text_box.insert(tk.END, f"无法获得【{model_name}】 的反馈，请用户操作\n", tag)
        except queue.Empty:
            pass
        self.root.after(STEP_INTERVAL, self.process_result_queue)

    def model_move(self):
        """
        模型进行落子。
        """
        model_name = self.models[(self.current_player - 1) % 2]
        tag = "model1" if (self.current_player - 1) % 2 == 0 else "model2"
        color = "黑" if self.current_player == 1 else "白"

        # 添加思考中提示
        self.text_box.insert(tk.END, f"【{model_name}】 执{color}棋，正在思考中...\n", tag)

        # 使用线程来获取模型决策
        thread = threading.Thread(target=self.threaded_model_move, args=(model_name, color, tag))
        thread.start()

        # 处理队列中的结果
        self.process_result_queue()

    def threaded_model_move(self, model_name, color, tag):
        """
        线程函数，用于获取模型决策。

        :param model_name: 模型名称
        :param color: 玩家颜色
        :param tag: 文本标签
        """
        row, col, error, result = self.get_move_from_model(model_name, self.board)
        self.result_queue.put((row, col, error, result, model_name, color, tag))

    def show_win_message(self, player):
        """
        显示游戏结束消息，并询问是否再来一局。

        :param player: 获胜玩家编号
        """
        player_name = self.get_player_color(player)
        result = messagebox.askyesno("游戏结束", f"{player_name} 棋获胜！是否再来一局？")
        if result:
            # 更新得分，胜利加5分
            if player == BLACK_PLAYER:
                self.black_score += 5
            else:
                self.white_score += 5
            # 更新记分牌显示
            self.score_board.config(text=f"黑棋: {self.black_score}  白棋: {self.white_score}")
            self.reset_game()
        else:
            self.root.destroy()

    def reset_game(self):
        """
        重置游戏。
        """
        # 清空棋盘
        self.canvas.delete("all")
        self.draw_board()
        # 重置棋盘状态
        self.board = [[0] * BOARD_SIZE for _ in range(BOARD_SIZE)]
        # 重置当前玩家
        self.current_player = 1
        # 清空消息栏
        self.text_box.delete(1.0, tk.END)
        # 重置预点击虚框
        self.preview_rect = None
        # 让第一个模型先落子
        self.model_move()

if __name__ == "__main__":
    root = tk.Tk()
    game = GomokuGame(root)
    root.mainloop()