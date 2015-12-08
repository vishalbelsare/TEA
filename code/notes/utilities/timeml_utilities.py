
import xml.etree.ElementTree as ET
from note_utils import valid_path

import xml_utilities

from string import whitespace

import re

def get_text_element(timeml_doc):

    root = xml_utilities.get_root(timeml_doc)

    text_element = None

    for e in root:
        if e.tag == "TEXT":

            text_element = e
            break

    return text_element


def get_text_element_from_root(timeml_root):

    # exit("called get text element from root")

    text_element = None

    for e in timeml_root:
        if e.tag == "TEXT":

            text_element = e
            break

    return text_element


def set_text_element(timeml_root, text_element):

    for e in timeml_root:
        if e.tag == "TEXT":

            e = text_element
            break

    return timeml_root

def annotate_text_element(timeml_root, tag, start, end, attributes = {}):
    '''
    returns modified version of the passed timeml_doc root with the annotations
    added in the correct positions
    '''

    text_element = get_text_element_from_root(timeml_root)

    element = ET.Element(tag, attributes)

    text = text_element.text

    start = start + 1
    end = end + 2

    newText = text[:start]
    eleText = text[start:end]
    tail = text[end:]

    text_element.text = newText
    element.text = eleText
    element.tail = tail

    text_element.insert(0, element)

    return text_element


def annotate_root(timeml_root, tag, attributes = {}):
    ''' adds a sub element to root'''

    element = ET.Element(tag, attributes)
    element.tail = "\n"

    timeml_root.append(element)

    return timeml_root

def get_text_with_taggings(timeml_doc):

    text_e = get_text_element(timeml_doc)

    string = ET.tostring(text_e)

    for char in ['\n'] + list(whitespace):

        string = string.strip(char)

    string = xml_utilities.strip_quotes(string)

    return string

def get_text(timeml_doc):
    """ gets raw text of document, xml tags removed """

    text_e = get_text_element(timeml_doc)

    string =  ET.tostring(text_e)

    string = ET.tostring(text_e, encoding='utf8', method='text')

    for char in ['\n'] + list(whitespace):

        string = string.strip(char)

    string = xml_utilities.strip_quotes(string)

    return string

def get_tagged_entities(timeml_doc):
    """ gets tagged entities within timeml text """

    text_element = get_text_element(timeml_doc)

    elements = []

    for element in text_element:

        elements.append(element)

    return elements

def get_make_instances(timeml_doc):
    """ gets the event instances in a timeml doc """
    root = xml_utilities.get_root(timeml_doc)

    make_instances = []

    for e in root:

        if e.tag == "MAKEINSTANCE":
            make_instances.append(e)

    return make_instances


def get_tlinks(timeml_doc):

    """ get tlinks from annotated document """

    root = xml_utilities.get_root(timeml_doc)

    tlinks = []

    for e in root:

        if e.tag == "TLINK":

            tlinks.append(e)

    return tlinks

def get_doctime_timex(timeml_doc):

    """ get the document creation time timex """

    root = xml_utilities.get_root(timeml_doc)

    doctime = None

    for e in root:

        if e.tag == "DCT":
            doctime = e[0]
            break

    return doctime

if __name__ == "__main__":

    doc = "/data2/kwacome/Temporal-Entity-Annotator-TEA-/bad_train_file/NYT19981121.0173.tml"

    e =  get_text_element(doc)

    print get_text(doc)
    print "\n\n\n"
    print get_text_with_taggings(doc)

    print "nothing to do here"

# EOF

