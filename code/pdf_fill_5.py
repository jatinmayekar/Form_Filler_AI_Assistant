import fillpdf
from fillpdf import fillpdfs
from pdfrw import PdfReader
from pdf_fill_write import write_fillable_pdf_for_page_number

import sys
import os

# input_pdf_path = 'test_full_1.pdf'
# input_pdf_path1 = 'fill_form_1.pdf'
# input_pdf_path2 = 'test_full_2-4-5.pdf'
# input_pdf_path3 = 'test_full_2-4-5-2.pdf'
#
# output_pdf_path = 'fill_form_1_Complete.pdf'
#
# page_number = 4
#
#
# def get_fields_from_current_page():
#     # fields = fillpdfs.get_form_fields(input_pdf_path2, page_number=2)
#     fields = fillpdfs.get_form_fields(input_pdf_path3)
#     print("fields: ", fields)
#
#
# get_fields_from_current_page()

x = PdfReader('Parthshastra_For Print_V2_editable_OG.pdf')

# for i in range(7):
#     page = x.pages[i]
#     print(f"Page {i} annotations: {page['/Annots']}")

#page = x.pages[5]['/Annots'][0]['/T']
#page = x.pages[5]
#print(page)

import pdfrw

ANNOT_KEY = '/Annots'               # key for all annotations within a page
ANNOT_FIELD_KEY = '/T'              # Name of field. i.e. given ID of field
ANNOT_FORM_type = '/FT'             # Form type (e.g. text/button)
ANNOT_FORM_button = '/Btn'          # ID for buttons, i.e. a checkbox
ANNOT_FORM_text = '/Tx'             # ID for textbox
ANNOT_FORM_options = '/Opt'
ANNOT_FORM_combo = '/Ch'
SUBTYPE_KEY = '/Subtype'
WIDGET_SUBTYPE_KEY = '/Widget'
ANNOT_FIELD_PARENT_KEY = '/Parent'  # Parent key for older pdf versions
ANNOT_FIELD_KIDS_KEY = '/Kids'      # Kids key for older pdf versions
ANNOT_VAL_KEY = '/V'
ANNOT_RECT_KEY = '/Rect'


def get_form_fields(input_pdf_path, sort=False, page_number=None):
    """
    Retrieves the form fields from a PDF and stores them in a dictionary.

    Parameters:
    - input_pdf_path (str): Path to the PDF file.
    - sort (bool, optional): If True, return the fields sorted by their keys. Defaults to False.
    - page_number (int, optional): Specifies the page number from which to extract fields.
                                   If None, extracts from all pages. Defaults to None.

    Returns:
    - dict: A dictionary of form fields and their values.
    """
    data_dict = {}
    pdf = pdfrw.PdfReader(input_pdf_path)

    # Validate page_number if provided
    if page_number is not None:
        if not isinstance(page_number, int) or page_number < 1 or page_number > len(pdf.pages):
            raise ValueError(f"Page number must be an integer between 1 and {len(pdf.pages)}.")

    for i, page in enumerate(pdf.pages, start=1):
        # Process only the specified page if page_number is provided
        if page_number is not None and i != page_number:
            continue

        annotations = page[ANNOT_KEY]
        if annotations:
            for annotation in annotations:
                if annotation[SUBTYPE_KEY] == WIDGET_SUBTYPE_KEY:
                    if annotation[ANNOT_FIELD_KEY]:
                        key = annotation[ANNOT_FIELD_KEY][1:-1]
                        data_dict[key] = ''
                        if annotation[ANNOT_VAL_KEY]:
                            value = annotation[ANNOT_VAL_KEY]
                            data_dict[key] = annotation[ANNOT_VAL_KEY]
                            try:
                                if type(annotation[ANNOT_VAL_KEY]) == pdfrw.objects.pdfstring.PdfString:
                                    data_dict[key] = pdfrw.objects.PdfString.decode(annotation[ANNOT_VAL_KEY])
                                elif type(annotation[ANNOT_VAL_KEY]) == pdfrw.objects.pdfname.BasePdfName:
                                    if '/' in annotation[ANNOT_VAL_KEY]:
                                        data_dict[key] = annotation[ANNOT_VAL_KEY][1:]
                            except:
                                pass
                    elif annotation['/AP']:
                        if not annotation['/T']:
                            annotation = annotation['/Parent']
                        key = annotation['/T'].to_unicode()
                        data_dict[key] = annotation[ANNOT_VAL_KEY]
                        try:
                            if type(annotation[ANNOT_VAL_KEY]) == pdfrw.objects.pdfstring.PdfString:
                                data_dict[key] = pdfrw.objects.PdfString.decode(annotation[ANNOT_VAL_KEY])
                            elif type(annotation[ANNOT_VAL_KEY]) == pdfrw.objects.pdfname.BasePdfName:
                                if '/' in annotation[ANNOT_VAL_KEY]:
                                    data_dict[key] = annotation[ANNOT_VAL_KEY][1:]
                        except:
                            pass
        # Break after processing the specified page
        if page_number is not None and i == page_number:
            break

    if sort:
        return dict(sorted(data_dict.items()))
    else:
        return data_dict


def extract_field_name(field):
    """
    Extracts and decodes the field name from a PDF annotation.
    """
    try:
        return pdfrw.objects.PdfString.decode(field) if field else ''
    except AttributeError:
        return field if isinstance(field, str) else ''


def extract_field_value(annotation):
    """
    Extracts and decodes the field value from a PDF annotation.
    """
    field_value = annotation.get(ANNOT_VAL_KEY, '')
    try:
        if isinstance(field_value, pdfrw.objects.pdfstring.PdfString):
            return pdfrw.objects.PdfString.decode(field_value)
        elif isinstance(field_value, pdfrw.objects.pdfname.BasePdfName) and '/' in field_value:
            return field_value[1:]
    except Exception as e:
        print(f"Error decoding field value: {e}")
    return field_value

pgn = 4
print("\n My function: ", get_form_fields('Parthshastra_For Print_V2_editable_OG.pdf', page_number=pgn))
print("\n")
print("\n Og function: ", fillpdfs.get_form_fields('Parthshastra_For Print_V2_editable_OG.pdf', page_number=pgn))
