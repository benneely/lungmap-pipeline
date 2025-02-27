import tkinter as tk
import ttkthemes as themed_tk
from tkinter import filedialog, ttk
import threading
import PIL.Image
import PIL.ImageTk
import json
import numpy as np
import lungmap_utils
from micap import utils as micap_utils, pipeline
from gui import utils as gui_utils

ontology = gui_utils.onto

# weird import style to un-confuse PyCharm
try:
    from cv2 import cv2
except ImportError:
    import cv2

BACKGROUND_COLOR = '#ededed'
BORDER_COLOR = '#bebebe'
HIGHLIGHT_COLOR = '#5294e2'
REGION_COLORS = {
    'candidate': '#ff8000',
    'current_label': '#00ff00',
    'other_label': '#ff00ff'
}

WINDOW_WIDTH = 820
WINDOW_HEIGHT = 920

PAD_SMALL = 2
PAD_MEDIUM = 4
PAD_LARGE = 8

DEV_STAGES = [
    "E16.5",
    "E18.5",
    "P01",
    "P03",
    "P07"
]

MAG_VALUES = [
    "20X",
    "60X",
    "100X"
]

SCALE_VALUES = [
    "0.25",
    "0.50",
    "0.75",
    "1.00"
]

PROBES = lungmap_utils.client.get_probes()


class ProgressCallable(object):
    def __init__(self, progress_var):
        self.progress_var = progress_var

    def __call__(self, progress):
        scaled_progress = int(progress * 100)
        self.progress_var.set(scaled_progress)


class Application(tk.Frame):

    def __init__(self, master):

        tk.Frame.__init__(self, master=master)

        self.master.minsize(width=WINDOW_WIDTH, height=WINDOW_HEIGHT)
        self.master.config(bg=BACKGROUND_COLOR)
        self.master.title("LungMAP Region Generator")

        check_button_style = ttk.Style()
        check_button_style.configure(
            'Default.TCheckbutton',
            background=BACKGROUND_COLOR
        )

        self.images = {}
        self.image_dims = None
        self.lm_query_top = None
        self.img_region_lut = {}
        self.current_img = None
        self.tk_image = None

        self.current_dev_stage = tk.StringVar(self.master)
        self.current_dev_stage.set(DEV_STAGES[0])
        self.current_mag = tk.StringVar(self.master)
        self.current_mag.set(MAG_VALUES[0])
        self.current_probe1 = tk.StringVar(self.master)
        self.current_probe1.set('Anti-Acta2')
        self.current_probe2 = tk.StringVar(self.master)
        self.current_probe3 = tk.StringVar(self.master)
        self.display_preprocessed = tk.BooleanVar(self.master)
        self.hide_other = tk.BooleanVar(self.master)
        self.hide_unlabelled = tk.BooleanVar(self.master)
        self.status_message = tk.StringVar(self.master)
        self.current_label = tk.StringVar(self.master)
        self.canvas_scale = tk.StringVar(self.master)
        self.canvas_scale.set('1.00')
        self.status_progress = tk.IntVar(self.master)

        self.dev_stage_option = None
        self.mag_option = None
        self.probe1_option = None
        self.probe2_option = None
        self.probe3_option = None
        self.query_results_list_box = None
        self.queried_images = {}
        self.download_progress_bar = None
        self.ref_img_name = None

        main_frame = tk.Frame(self.master, bg=BACKGROUND_COLOR)
        main_frame.pack(
            fill='both',
            expand=True,
            anchor='n',
            padx=0,
            pady=0
        )

        file_chooser_frame = tk.Frame(main_frame, bg=BACKGROUND_COLOR)
        file_chooser_frame.pack(
            fill=tk.X,
            expand=False,
            anchor=tk.N,
            padx=PAD_MEDIUM,
            pady=PAD_MEDIUM
        )

        image_toolbar_frame = tk.Frame(main_frame, bg=BACKGROUND_COLOR)
        image_toolbar_frame.pack(
            fill=tk.X,
            expand=False,
            anchor=tk.N,
            padx=PAD_LARGE,
            pady=PAD_SMALL
        )

        bottom_frame = tk.Frame(main_frame, bg=BACKGROUND_COLOR)
        bottom_frame.pack(
            fill='both',
            expand=True,
            anchor='n',
            padx=PAD_MEDIUM,
            pady=PAD_SMALL
        )

        file_chooser_button_frame = tk.Frame(
            file_chooser_frame,
            bg=BACKGROUND_COLOR
        )

        add_image_button = ttk.Button(
            file_chooser_button_frame,
            text='Load Images',
            command=self.display_image_query_dialog
        )
        add_image_button.pack(side=tk.LEFT)

        self.preprocess_images_button = ttk.Button(
            file_chooser_button_frame,
            text='Pre-process Images',
            command=self.preprocess_images
        )
        self.preprocess_images_button.pack(side=tk.LEFT)

        save_regions_button = ttk.Button(
            file_chooser_button_frame,
            text='Save Regions',
            command=self.save_regions_json
        )
        save_regions_button.pack(side=tk.RIGHT, anchor=tk.N)

        file_chooser_button_frame.pack(
            anchor='n',
            fill='x',
            expand=False,
            padx=PAD_MEDIUM,
            pady=PAD_MEDIUM
        )

        file_list_frame = tk.Frame(
            file_chooser_frame,
            bg=BACKGROUND_COLOR,
            highlightcolor=HIGHLIGHT_COLOR,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1
        )
        file_scroll_bar = ttk.Scrollbar(file_list_frame, orient='vertical')
        self.file_list_box = tk.Listbox(
            file_list_frame,
            exportselection=False,
            height=4,
            yscrollcommand=file_scroll_bar.set,
            relief='flat',
            borderwidth=0,
            highlightthickness=0,
            selectbackground=HIGHLIGHT_COLOR,
            selectforeground='#ffffff'
        )
        self.file_list_box.bind('<<ListboxSelect>>', self.select_image)
        file_scroll_bar.config(command=self.file_list_box.yview)
        file_scroll_bar.pack(side='right', fill='y')
        self.file_list_box.pack(fill='x', expand=True)

        file_list_frame.pack(
            fill='x',
            expand=False,
            padx=PAD_MEDIUM,
            pady=PAD_SMALL
        )

        self.find_regions_button = ttk.Button(
            image_toolbar_frame,
            text='Find Regions',
            command=self.find_regions
        )
        self.find_regions_button.pack(side=tk.LEFT, anchor=tk.N)

        display_preprocessed_cb = ttk.Checkbutton(
            image_toolbar_frame,
            text="Display pre-processed image",
            variable=self.display_preprocessed,
            style='Default.TCheckbutton',
            command=self.select_image
        )
        display_preprocessed_cb.pack(
            side=tk.LEFT,
            padx=PAD_MEDIUM
        )

        ttk.Separator(
            image_toolbar_frame,
            orient=tk.VERTICAL
        ).pack(
            side=tk.LEFT,
            fill='y',
            padx=PAD_MEDIUM
        )

        ttk.Label(
            image_toolbar_frame,
            text="Scale image:",
            background=BACKGROUND_COLOR
        ).pack(
            side=tk.LEFT,
            fill='none',
            expand=False,
            padx=PAD_MEDIUM
        )
        scale_option = ttk.Combobox(
            image_toolbar_frame,
            values=SCALE_VALUES,
            textvariable=self.canvas_scale,
            state='readonly',
            width=4
        )
        scale_option.bind('<<ComboboxSelected>>', self.select_image)
        scale_option.pack(
            side=tk.LEFT,
            fill='none',
            expand=False,
            padx=PAD_MEDIUM
        )

        ttk.Separator(
            image_toolbar_frame,
            orient=tk.VERTICAL
        ).pack(
            side=tk.LEFT,
            fill='y',
            padx=PAD_MEDIUM
        )

        hide_other_cb = ttk.Checkbutton(
            image_toolbar_frame,
            text="Hide other labels",
            variable=self.hide_other,
            style='Default.TCheckbutton',
            command=self.select_image
        )
        hide_other_cb.pack(
            side=tk.LEFT,
            padx=PAD_MEDIUM
        )

        ttk.Separator(
            image_toolbar_frame,
            orient=tk.VERTICAL
        ).pack(
            side=tk.LEFT,
            fill='y',
            padx=PAD_MEDIUM
        )

        hide_unlabelled_cb = ttk.Checkbutton(
            image_toolbar_frame,
            text="Hide unlabelled",
            variable=self.hide_unlabelled,
            style='Default.TCheckbutton',
            command=self.select_image
        )
        hide_unlabelled_cb.pack(
            side=tk.LEFT,
            padx=PAD_MEDIUM
        )

        self.label_option = ttk.Combobox(
            image_toolbar_frame,
            textvariable=self.current_label,
            state='readonly'
        )
        self.label_option.bind('<<ComboboxSelected>>', self.select_label)
        self.label_option.pack(side=tk.RIGHT, fill='x', expand=False)

        ttk.Label(
            image_toolbar_frame,
            text="Assign label:",
            background=BACKGROUND_COLOR
        ).pack(
            side=tk.RIGHT,
            fill='none',
            expand=False,
            padx=PAD_MEDIUM
        )

        ttk.Separator(
            image_toolbar_frame,
            orient=tk.VERTICAL
        ).pack(
            side=tk.RIGHT,
            fill='y',
            padx=PAD_MEDIUM
        )

        # the canvas frame's contents will use grid b/c of the double
        # scrollbar (they don't look right using pack), but the canvas itself
        # will be packed in its frame
        canvas_frame = tk.Frame(bottom_frame, bg=BACKGROUND_COLOR)
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)
        canvas_frame.pack(
            fill=tk.BOTH,
            expand=True,
            anchor=tk.N,
            side='right',
            padx=PAD_MEDIUM,
            pady=PAD_MEDIUM
        )

        self.canvas = tk.Canvas(
            canvas_frame,
            cursor="tcross",
            takefocus=1
        )

        self.scrollbar_v = ttk.Scrollbar(
            canvas_frame,
            orient=tk.VERTICAL
        )
        self.scrollbar_h = ttk.Scrollbar(
            canvas_frame,
            orient=tk.HORIZONTAL
        )
        self.scrollbar_v.config(command=self.canvas.yview)
        self.scrollbar_h.config(command=self.canvas.xview)

        self.canvas.config(yscrollcommand=self.scrollbar_v.set)
        self.canvas.config(xscrollcommand=self.scrollbar_h.set)

        self.canvas.grid(
            row=0,
            column=0,
            sticky=tk.N + tk.S + tk.E + tk.W
        )
        self.scrollbar_v.grid(row=0, column=1, sticky=tk.N + tk.S)
        self.scrollbar_h.grid(row=1, column=0, sticky=tk.E + tk.W)

        self.canvas.bind("<Button-1>", self.select_region)
        self.canvas.bind("<ButtonPress-2>", self.on_pan_button_press)
        self.canvas.bind("<B2-Motion>", self.pan_image)
        self.canvas.bind("<ButtonRelease-2>", self.on_pan_button_release)
        self.canvas.bind("<ButtonPress-3>", self.on_pan_button_press)
        self.canvas.bind("<B3-Motion>", self.pan_image)
        self.canvas.bind("<ButtonRelease-3>", self.on_pan_button_release)

        self.pan_start_x = None
        self.pan_start_y = None

        status_progress_frame = tk.Frame(main_frame, bg=BACKGROUND_COLOR)
        status_progress_frame.pack(
            fill='x',
            expand=False,
            anchor=tk.S,
            padx=PAD_SMALL,
            pady=PAD_SMALL
        )
        self.status_progress_bar = ttk.Progressbar(
            status_progress_frame,
            variable=self.status_progress
        )
        self.status_progress_bar.pack(
            anchor=tk.S,
            fill='x',
            expand=False
        )

        status_frame = tk.Frame(main_frame)
        status_frame.config(
            highlightbackground=BORDER_COLOR,
            highlightthickness=1
        )
        status_frame.pack(
            fill='x',
            expand=False,
            anchor=tk.S,
            padx=0,
            pady=0
        )

        self.status_label = ttk.Label(
            status_frame,
            textvariable=self.status_message
        )
        self.status_label.config(background='#fafafa')
        self.status_label.pack(
            fill='x',
            expand=False,
            anchor=tk.W,
            padx=0,
            pady=0
        )

        self.pack()

    def display_image_query_dialog(self):
        lm_query_top = tk.Toplevel(bg=BACKGROUND_COLOR)
        lm_query_top.minsize(height=360, width=720)

        metadata_options_frame = tk.Frame(lm_query_top, bg=BACKGROUND_COLOR)
        metadata_options_frame.pack(
            fill=tk.X,
            expand=False,
            anchor=tk.N,
            padx=PAD_MEDIUM,
            pady=PAD_MEDIUM
        )

        metadata_options_left_frame = tk.Frame(
            metadata_options_frame,
            bg=BACKGROUND_COLOR
        )
        metadata_options_left_frame.pack(
            fill=tk.X,
            expand=False,
            anchor=tk.N,
            side=tk.LEFT,
            padx=PAD_MEDIUM,
            pady=PAD_MEDIUM
        )
        metadata_options_right_frame = tk.Frame(
            metadata_options_frame,
            bg=BACKGROUND_COLOR
        )
        metadata_options_right_frame.pack(
            fill=tk.X,
            expand=False,
            anchor=tk.N,
            side=tk.RIGHT,
            padx=PAD_MEDIUM,
            pady=PAD_MEDIUM
        )

        dev_stage_frame = tk.Frame(
            metadata_options_left_frame,
            bg=BACKGROUND_COLOR
        )
        dev_stage_frame.pack(
            fill=tk.X,
            expand=False,
            side=tk.TOP,
            padx=PAD_MEDIUM,
            pady=PAD_MEDIUM
        )

        ttk.Label(
            dev_stage_frame,
            text="Development Stage:",
            background=BACKGROUND_COLOR
        ).pack(side=tk.LEFT)
        self.dev_stage_option = ttk.Combobox(
            dev_stage_frame,
            textvariable=self.current_dev_stage,
            state='readonly'
        )
        self.dev_stage_option['values'] = sorted(DEV_STAGES)
        self.dev_stage_option.pack(side=tk.RIGHT, fill='x', expand=False)

        mag_frame = tk.Frame(
            metadata_options_left_frame,
            bg=BACKGROUND_COLOR
        )
        mag_frame.pack(
            fill=tk.X,
            expand=False,
            side=tk.TOP,
            padx=PAD_MEDIUM,
            pady=PAD_MEDIUM
        )

        ttk.Label(
            mag_frame,
            text="Magnification:",
            background=BACKGROUND_COLOR
        ).pack(side=tk.LEFT)
        self.mag_option = ttk.Combobox(
            mag_frame,
            textvariable=self.current_mag,
            state='readonly'
        )
        self.mag_option['values'] = MAG_VALUES
        self.mag_option.pack(side=tk.RIGHT, fill='x', expand=False)

        probe1_frame = tk.Frame(
            metadata_options_right_frame,
            bg=BACKGROUND_COLOR
        )
        probe1_frame.pack(
            fill=tk.X,
            expand=False,
            side=tk.TOP,
            padx=PAD_MEDIUM,
            pady=PAD_MEDIUM
        )

        ttk.Label(
            probe1_frame,
            text="Probe 1:",
            background=BACKGROUND_COLOR
        ).pack(side=tk.LEFT)
        self.probe1_option = ttk.Combobox(
            probe1_frame,
            textvariable=self.current_probe1,
            state='readonly'
        )
        self.probe1_option['values'] = sorted(PROBES)
        self.probe1_option.pack(side=tk.RIGHT, fill='x', expand=False)

        probe2_frame = tk.Frame(
            metadata_options_right_frame,
            bg=BACKGROUND_COLOR
        )
        probe2_frame.pack(
            fill=tk.X,
            expand=False,
            side=tk.TOP,
            padx=PAD_MEDIUM,
            pady=PAD_MEDIUM
        )

        ttk.Label(
            probe2_frame,
            text="Probe 2:",
            background=BACKGROUND_COLOR
        ).pack(side=tk.LEFT)
        self.probe2_option = ttk.Combobox(
            probe2_frame,
            textvariable=self.current_probe2,
            state='readonly'
        )
        self.probe2_option['values'] = sorted(PROBES)
        self.probe2_option.pack(side=tk.RIGHT, fill='x', expand=False)

        probe3_frame = tk.Frame(
            metadata_options_right_frame,
            bg=BACKGROUND_COLOR
        )
        probe3_frame.pack(
            fill=tk.X,
            expand=False,
            side=tk.TOP,
            padx=PAD_MEDIUM,
            pady=PAD_MEDIUM
        )

        ttk.Label(
            probe3_frame,
            text="Probe 3:",
            background=BACKGROUND_COLOR
        ).pack(side=tk.LEFT)
        self.probe3_option = ttk.Combobox(
            probe3_frame,
            textvariable=self.current_probe3,
            state='readonly'
        )
        self.probe3_option['values'] = sorted(PROBES)
        self.probe3_option.pack(side=tk.RIGHT, fill='x', expand=False)

        query_button_frame = tk.Frame(lm_query_top, bg=BACKGROUND_COLOR)
        query_button_frame.pack(
            fill='x',
            expand=False,
            anchor=tk.N,
            padx=PAD_SMALL,
            pady=PAD_SMALL
        )
        query_button = ttk.Button(
            query_button_frame,
            text="Run Query",
            command=self.query_images
        )
        query_button.pack(anchor=tk.E)

        file_chooser_frame = tk.Frame(lm_query_top, bg=BACKGROUND_COLOR)
        file_chooser_frame.pack(
            fill='both',
            expand=True,
            anchor=tk.N,
            padx=PAD_MEDIUM,
            pady=PAD_MEDIUM
        )

        query_results_frame = tk.Frame(
            file_chooser_frame,
            bg=BACKGROUND_COLOR,
            highlightcolor=HIGHLIGHT_COLOR,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1
        )
        query_results_scroll_bar = ttk.Scrollbar(query_results_frame, orient='vertical')
        self.query_results_list_box = tk.Listbox(
            query_results_frame,
            exportselection=False,
            height=4,
            yscrollcommand=query_results_scroll_bar.set,
            relief='flat',
            borderwidth=0,
            highlightthickness=0,
            selectbackground=HIGHLIGHT_COLOR,
            selectforeground='#ffffff'
        )
        query_results_scroll_bar.config(command=self.file_list_box.yview)
        query_results_scroll_bar.pack(side='right', fill='y')
        self.query_results_list_box.pack(fill='both', expand=True)

        query_results_frame.pack(
            fill='both',
            expand=True,
            padx=PAD_MEDIUM,
            pady=PAD_SMALL
        )

        bottom_frame = tk.Frame(lm_query_top, bg=BACKGROUND_COLOR)
        bottom_frame.pack(
            fill='x',
            expand=False,
            anchor='n',
            padx=PAD_MEDIUM,
            pady=PAD_MEDIUM
        )

        progress_frame = tk.Frame(bottom_frame, bg=BACKGROUND_COLOR)
        progress_frame.pack(
            fill='both',
            expand=True,
            anchor=tk.S,
            side=tk.LEFT,
            padx=PAD_MEDIUM,
            pady=PAD_MEDIUM
        )
        self.download_progress_bar = ttk.Progressbar(progress_frame)
        self.download_progress_bar.pack(
            anchor=tk.S,
            fill='x',
            expand=True
        )

        done_button = ttk.Button(bottom_frame, text="Done", command=lm_query_top.destroy)
        done_button.pack(
            anchor=tk.E,
            side=tk.RIGHT,
            expand=False,
            padx=PAD_MEDIUM,
            pady=PAD_MEDIUM
        )

        download_button = ttk.Button(bottom_frame, text="Download Images", command=self.download_images)
        download_button.pack(
            anchor=tk.E,
            side=tk.RIGHT,
            expand=False,
            padx=PAD_MEDIUM,
            pady=PAD_MEDIUM
        )

    def query_images(self):
        dev_stage = self.current_dev_stage.get()
        mag = self.current_mag.get()
        probe1 = self.current_probe1.get()
        probe2 = self.current_probe2.get()
        probe3 = self.current_probe3.get()
        probes = [probe1, probe2, probe3]

        # TODO: show error dialog if any metadata field was not selected

        lm_images = lungmap_utils.client.get_images_by_metadata(
            dev_stage, mag, probes
        )

        # will query ontology structures here b/c we can do it once for
        # all these images instead of for each image
        probe_structure_dict = gui_utils.get_probe_structure_map(
            ontology,
            probes
        )

        # clear the list box & queried_images
        self.query_results_list_box.delete(0, tk.END)
        self.queried_images = {}
        for img in lm_images:
            url_parts = img['image_url']['value'].split('/')
            image_name = url_parts[-1]

            probe_colors = [
                img['color1']['value'],
                img['color2']['value'],
                img['color3']['value']
            ]

            self.queried_images[image_name] = {
                'url': img['image_url']['value'],
                'dev_stage': dev_stage,
                'mag': mag,
                'probes': probes,
                'probe_colors': probe_colors,
                'probe_structure_map': probe_structure_dict
            }

            self.query_results_list_box.insert(tk.END, image_name)

    def download_images(self):
        self.download_progress_bar.config(maximum=len(self.queried_images))
        for img_name, img_dict in sorted(self.queried_images.items()):
            image_name, tmp_img = lungmap_utils.client.get_image_from_lungmap(
                img_dict['url']
            )

            cv_img = cv2.imdecode(
                np.frombuffer(
                    tmp_img,
                    dtype=np.uint8
                ),
                cv2.IMREAD_COLOR
            )

            rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
            hsv_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2HSV)

            self.images[image_name] = {
                'rgb_img': rgb_image,
                'hsv_img': hsv_image,
                'corr_rgb_img': None,
                'dev_stage': img_dict['dev_stage'],
                'mag': img_dict['mag'],
                'probes': img_dict['probes'],
                'probe_colors': img_dict['probe_colors'],
                'probe_structure_map': img_dict['probe_structure_map']
            }
            self.file_list_box.insert(tk.END, image_name)

            # update progress bar
            self.download_progress_bar.step()
            self.download_progress_bar.update()

    def _preprocess_images(self):
        sorted_img_names = sorted(self.images.keys())

        # for progress status updates
        process_count = len(sorted_img_names) * 2
        progress = 0
        self.status_progress.set(0)

        luminance_corrected_imgs = []
        for img_name in sorted_img_names:
            lum_corr_img = micap_utils.non_uniformity_correction(
                self.images[img_name]['hsv_img']
            )
            luminance_corrected_imgs.append(lum_corr_img)

            progress += 1
            scaled_progress = int((progress / float(process_count)) * 100)
            self.status_progress.set(scaled_progress)

        ref_img_idx = micap_utils.find_color_correction_reference(
            luminance_corrected_imgs
        )
        self.ref_img_name = sorted_img_names[ref_img_idx]

        progress += 1
        scaled_progress = int((progress / float(process_count)) * 100)
        self.status_progress.set(scaled_progress)

        corr_rgb_imgs = micap_utils.color_correction(
            luminance_corrected_imgs,
            ref_img_idx
        )

        for i, img_name in enumerate(sorted_img_names):
            self.images[img_name]['corr_rgb_img'] = corr_rgb_imgs[i]

        self.status_progress.set(100)

        self.preprocess_images_button.config(state=tk.NORMAL)
        self.status_message.set("Pre-processing finished")

    def preprocess_images(self):
        self.status_message.set("Pre-processing images...")
        self.preprocess_images_button.config(state=tk.DISABLED)
        threading.Thread(target=self._preprocess_images, daemon=True).start()

    # noinspection PyUnusedLocal
    def select_image(self, event=None):
        current_sel = self.file_list_box.curselection()

        if len(current_sel) == 0:
            return
        self.current_img = self.file_list_box.get(current_sel[0])

        has_corr = self.images[self.current_img]['corr_rgb_img'] is not None
        display_corr = self.display_preprocessed.get()
        structures = self.images[self.current_img]['probe_structure_map']

        display_structures = set()

        for probe, structure_map in structures.items():
            for s in structure_map['surrounded_by']:
                display_structures.add(s)
            for s in structure_map['has_part']:
                display_structures.add(s)

        self.label_option['values'] = sorted(display_structures)

        if has_corr and display_corr:
            img_to_display = self.images[self.current_img]['corr_rgb_img']
        else:
            img_to_display = self.images[self.current_img]['rgb_img']

        image = PIL.Image.fromarray(
            img_to_display,
            'RGB'
        )
        height, width = image.size
        canvas_scale = float(self.canvas_scale.get())
        image = image.resize(
            (
                int(height * canvas_scale),
                int(width * canvas_scale)
            )
        )
        height, width = image.size
        self.tk_image = PIL.ImageTk.PhotoImage(image)
        self.image_dims = (height, width)
        self.canvas.config(scrollregion=(0, 0, height, width))
        self.canvas.create_image(
            0,
            0,
            anchor=tk.NW,
            image=self.tk_image
        )
        self.draw_regions()

    def draw_regions(self):
        if self.current_img not in self.img_region_lut:
            return

        img_region_map = self.img_region_lut[self.current_img]
        candidates = img_region_map['candidates']
        labels = img_region_map['labels']

        canvas_scale = float(self.canvas_scale.get())

        current_label = self.current_label.get()
        if current_label == '':
            current_label_code = -1
        else:
            current_label_code = self.label_option['values'].index(current_label)
            current_label_code += 1

        hide_other = self.hide_other.get()
        hide_unlabelled = self.hide_unlabelled.get()

        current_count = 0
        other_count = 0
        unlabelled_count = 0

        for i, c in enumerate(candidates):
            # label codes:
            #     candidate == 0 (means an unlabelled region)
            #     >0 means sorted labels index + 1
            if labels[i] == 0:
                region_type = 'candidate'
                stipple = None
                fill = ''
                unlabelled_count += 1
            elif labels[i] == current_label_code:
                region_type = 'current_label'
                stipple = 'gray12'
                fill = REGION_COLORS[region_type]
                current_count += 1
            else:
                region_type = 'other_label'
                stipple = 'gray25'
                fill = REGION_COLORS[region_type]
                other_count += 1

            if hide_other and region_type == 'other_label':
                continue
            if hide_unlabelled and region_type == 'candidate':
                continue

            self.canvas.create_polygon(
                list(c.flatten()),
                tags=("poly", str(i)),
                fill=fill,
                outline=REGION_COLORS[region_type],
                width=np.ceil(5 * canvas_scale),
                stipple=stipple
            )

        self.canvas.scale(tk.ALL, 0, 0, canvas_scale, canvas_scale)

        self.status_message.set(
            "Displaying %d regions, %d %s, %d other labels, %d unlabelled" % (
                len(candidates),
                current_count,
                current_label,
                other_count,
                unlabelled_count
            )
        )

    def run_segmentation(self, hsv_img, seg_config, cell_size):
        if self.current_img not in self.img_region_lut:
            self.img_region_lut[self.current_img] = {}
        progress_callback = ProgressCallable(self.status_progress)
        candidates = pipeline.generate_structure_candidates(
            hsv_img,
            seg_config,
            filter_min_size=3 * cell_size,
            dog_factor=7,
            process_residual=False,
            plot=False,
            progress_callback=progress_callback
        )

        self.img_region_lut[self.current_img]['candidates'] = candidates

        # candidate label = 0, structure labels = 1 -> len(structures)
        self.img_region_lut[self.current_img]['labels'] = list(
            np.zeros(len(candidates))
        )

        self.draw_regions()
        self.status_progress = 0
        self.find_regions_button.config(state=tk.NORMAL)

    def find_regions(self):
        # build micap pipeline, w/ seg stages based on 'has_part'
        # and 'surrounded_by' probe/structure mappings

        # first, check that an image is selected
        if self.current_img is None:
            return

        # build seg config for current image
        probes = self.images[self.current_img]['probes']
        probe_colors = [
            c.lower() for c in self.images[self.current_img]['probe_colors']
        ]
        probe_structure_map = self.images[self.current_img]['probe_structure_map']

        has_part_colors = set()

        for i, p in enumerate(probes):
            ps_map = probe_structure_map[p]

            if len(ps_map['has_part']) > 0:
                has_part_colors.add(probe_colors[i])

        non_has_part_colors = set(probe_colors).difference(has_part_colors)

        # because DAPI is blue, probe colors can get slightly mixed with blue
        # so we'll add the blue-ish version of each color for better results
        if 'green' in has_part_colors:
            has_part_colors.add('cyan')
        if 'red' in has_part_colors:
            has_part_colors.add('violet')
        if 'white' in has_part_colors:
            has_part_colors.add('gray')

        if 'green' in non_has_part_colors:
            non_has_part_colors.add('cyan')
        if 'red' in non_has_part_colors:
            non_has_part_colors.add('violet')
        if 'white' in non_has_part_colors:
            non_has_part_colors.add('gray')

        cell_radius = 16
        cell_size = np.pi * (cell_radius ** 2)

        seg_config = [
            # 1st seg stage uses 'has_part colors'
            {
                'type': 'color',
                'args': {
                    'blur_kernel': (15, 15),
                    'min_size': 3 * cell_size,
                    'max_size': None,
                    'colors': has_part_colors
                }
            },
            # 2nd - 4th stages are saturation stages of descending sizes
            {
                'type': 'saturation',
                'args': {'blur_kernel': (95, 95), 'min_size': 3 * cell_size, 'max_size': None}
            },
            {
                'type': 'saturation',
                'args': {'blur_kernel': (31, 31), 'min_size': 3 * cell_size, 'max_size': None}
            },
            {
                'type': 'saturation',
                'args': {'blur_kernel': (15, 15), 'min_size': 3 * cell_size, 'max_size': None}
            },
            # final stage is a color stage on the non has part colors
            {
                'type': 'color',
                'args': {
                    'blur_kernel': (7, 7),
                    'min_size': 3 * cell_size,
                    'max_size': None,
                    'colors': non_has_part_colors
                }
            },
        ]

        if self.images[self.current_img]['corr_rgb_img'] is not None:
            hsv_img = cv2.cvtColor(
                self.images[self.current_img]['corr_rgb_img'],
                cv2.COLOR_RGB2HSV
            )
        else:
            hsv_img = self.images[self.current_img]['hsv_img']

        self.status_message.set("Finding regions...")
        self.find_regions_button.config(state=tk.DISABLED)
        threading.Thread(
            target=self.run_segmentation,
            args=(hsv_img, seg_config, cell_size),
            daemon=True
        ).start()

    # noinspection PyUnusedLocal
    def select_label(self, event):
        self.clear_drawn_regions()
        self.draw_regions()

    def on_pan_button_press(self, event):
        self.canvas.config(cursor='fleur')

        # starting position for panning
        self.pan_start_x = int(self.canvas.canvasx(event.x))
        self.pan_start_y = int(self.canvas.canvasy(event.y))

    def pan_image(self, event):
        self.canvas.scan_dragto(
            event.x - self.pan_start_x,
            event.y - self.pan_start_y,
            gain=1
        )

    # noinspection PyUnusedLocal
    def on_pan_button_release(self, event):
        self.canvas.config(cursor='tcross')

    def clear_drawn_regions(self):
        self.canvas.delete("poly")

    def save_regions_json(self):
        save_file = filedialog.asksaveasfile(defaultextension=".json")
        if save_file is None:
            return

        def my_converter(o):
            if isinstance(o, np.ndarray):
                return o.tolist()

        json.dump(
            self.img_region_lut,
            save_file,
            indent=2,
            default=my_converter
        )

    # noinspection PyUnusedLocal
    def select_region(self, event):
        # first, check if a label has been selected. If not, do nothing.
        # If it has, determing the label code
        current_label = self.current_label.get()
        if current_label == '':
            return

        current_label_code = self.label_option['values'].index(current_label)
        current_label_code += 1

        # Next, check that the object is a polygon by the 'poly' tag we added
        current_cv_obj = self.canvas.find_withtag(tk.CURRENT)
        tags = self.canvas.gettags(current_cv_obj[0])

        if 'poly' not in tags:
            return

        # if it has a 'poly' tag, then the 2nd tag is our ID (index)
        # Set the corresponding region label to the current label idx + 1
        region_idx = int(tags[1])
        img_region_map = self.img_region_lut[self.current_img]
        labels = img_region_map['labels']
        labels[region_idx] = current_label_code

        # finally, redraw regions
        self.clear_drawn_regions()
        self.draw_regions()


root = themed_tk.ThemedTk()
root.set_theme('arc')
app = Application(root)
root.mainloop()
