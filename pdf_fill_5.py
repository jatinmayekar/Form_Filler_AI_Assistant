import fillpdf
from fillpdf import fillpdfs
from pdfrw import PdfReader
from pdf_fill_write import write_fillable_pdf_for_page_number

import sys
import os

input_pdf_path = 'fill_form_1.pdf'
output_pdf_path = 'fill_form_1_Complete.pdf'

class SuppressPrint:
    def __enter__(self):
        self._original_stdout = sys.stdout  # Backup original stdout
        sys.stdout = open(os.devnull, 'w')  # Redirect stdout to null device

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout.close()  # Close the stream
        sys.stdout = self._original_stdout  # Restore original stdout

def get_total_no_of_pages(input_pdf_path):
    return len(PdfReader(input_pdf_path).pages)

def find_latest_unfilled_page_with_fields(input_pdf_path):
    page_number = -1
    total_no_of_pages = get_total_no_of_pages(input_pdf_path)
    #print("Total no of pages: ", total_no_of_pages)

    for i in range(total_no_of_pages):
        flag = False
        with SuppressPrint():
            fields = fillpdfs.get_form_fields(input_pdf_path, page_number=i+1)
        for key, value in fields.items():
            if value != "":
                # page is filled, so skip and go to next page
                flag = True
                break
        if flag == False:
            # unfilled page found
            page_number = i+1
            break

    if page_number == -1:
        return None
    else:
        return page_number, fields
    
def set_fields(input_pdf_path, output_pdf_path, data_dict, page_number):
    write_fillable_pdf_for_page_number(input_pdf_path, output_pdf_path, data_dict, page_number, flatten=True)
    return output_pdf_path

def add_custom_function(input_pdf_path, output_pdf_path):
    return output_pdf_path

print(find_latest_unfilled_page_with_fields(input_pdf_path))

data_dict = {'Name': 'adada', 'Date of Birth': '34343', 'Address': '3fddefdfd', 'Mobile': '34343434', 'Telephone R': '', 'IT PANGIR No': '', 'Mobile_2': '', 'Blood Group': '', 'Email': '', 'Driving Licence No': '', 'Expires on': '', 'Passport No': '', 'Expires on_2': '', 'PFGPFEPFNPS No': '', 'Name_2': '', 'Date of Birth_2': '', 'Address_2': '', 'Mobile_3': '', 'Telephone R_2': '', 'IT PANGIR No_2': '', 'Mobile_4': '', 'Blood Group_2': '', 'Email_2': ''}
print(set_fields(input_pdf_path, output_pdf_path, data_dict, 1))

