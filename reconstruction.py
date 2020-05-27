"""
Pedurma Footnote Reconstruction
Footnote reconstruction script for the ocred katen pedurma using annotation transfer with 
google's dmp.(https://github.com/google/diff-match-patch) 
This script allows to transfer a specific set of annotations(footnotes and footnote markers) 
from text A(OCRed etext) to text B(clean etext). We first compute a diff between  texts 
A and B, then filter the annotations(dmp diffs) we want to transfer and then apply them to 
text B.

Tibetan alphabet:
- 


"""
import re
from itertools import zip_longest
import unicodedata
from pathlib import Path
from functools import partial
import yaml
from diff_match_patch import diff_match_patch
from preprocess_footnotes import preprocessGoogleNotes, preprocessNamselNotes


def preprocess_footnote(B, A):
    """Normalise edition markers to minimise noise in diffs.

    Args:
        target (str): Target text
        source (str): source text
    Returns:
        str: normalised target text
        str: normalised source text
    """
    patterns = [["〈〈?", "«"], ["〉〉?", "»"], ["《", "«"], ["》", "»"]]
    clean_N = B
    clean_G = A
    for pattern in patterns:
        clean_N = re.sub(pattern[0], pattern[1], clean_N)
        clean_G = re.sub(pattern[0], pattern[1], clean_G)
    return clean_N, clean_G


def rm_google_ocr_header(text):
    """Remove header of google ocr

    Args:
        text (str): google ocr

    Returns:
        str: header removed
    """
    header_pattern = "\n\n\n\n{1,18}.+\n(.{1,30}\n)?(.{1,15}\n)?(.{1,15}\n)?(.{1,15}\n)?"
    result = re.sub(header_pattern, "\n\n\n", text)
    return result


def get_diff(B, A):
    """Compute diff between target and source using DMP.

    Args:
        target (str): target text
        source (str): source text
    Returns:
        list: list of diffs
    """
    dmp = diff_match_patch()
    # Diff_timeout is set to 0 inorder to compute diff till end of file.
    dmp.Diff_Timeout = 0
    diffs = dmp.diff_main(B, A)
    # beautifies the diff list
    # dmp.diff_cleanupSemantic(diffs)
    print("Diff computation done.")
    return diffs


def to_yaml(list_, base_path, type_=None):
    """Dump list to yaml and write the yaml to a file on mentioned path.

    Args:
        list_ (list): list
        base_path (path): base path object
        type_ (str, optional): type of list you want to dump as yaml. Defaults to None.
    """
    print(f"Dumping {type_}...")
    list_yaml = yaml.safe_dump(list_, allow_unicode=True)
    list_yaml_path = base_path / f"{type_}.yaml"
    list_yaml_path.write_text(list_yaml, encoding="utf-8")
    print(f"{type_} Yaml saved...")


def rm_noise(diff):
    """Filter out noise from diff text.

    Args:
        diff (str): diff text
    Returns:
        str: cleaned diff text
    """
    result = diff
    patterns = [
        "\n",
        "\u0020+",
        "་+?",
    ]
    for pattern in patterns:
        noise = re.search(pattern, diff)
        if noise:
            result = result.replace(noise[0], "")
    return result


def rm_markers_ann(text):
    """Remove page annotation and replace footnotemarker with #.

    Args:
        text (str): diff applied text

    Returns:
        str: diff applied text without page annotation and replaced footnotemarker with #
    """
    result = ""
    lines = text.splitlines()
    for line in lines:
        line = re.sub("<p.+?>", "", line)
        line = re.sub("<.+?>", "#", line)
        result += line + "\n"
    return result


def get_pg_ann(diff, vol_num):
    """Extract pedurma pagination and put page annotation.

    Args:
        diff (str): diff text
        vol_num (int): volume number

    Returns:
        str: page annotation
    """

    pg_no_pattern = f"{vol_num}\S*?(\d+)"
    pg_pat = re.search(pg_no_pattern, diff)
    pg_num = pg_pat.group(1)
    return f"<p{vol_num}-{pg_num}>"


def get_abs_marker(diff):
    """Extract absolute footnote marker from diff text.

    Args:
        diff (str): diff text

    Returns:
        str: footnote marker
    """
    marker_ = ""
    patterns = [
        "[①-⑳]",
        "[༠-༩]+",
        "[0-9]+",
    ]
    for pattern in patterns:
        if marker := re.search(pattern, diff):
            marker_ += marker[0]
    return marker_


def get_excep_marker(diff):
    """Check is diff belong to exception marker or not if so returns it.

    Args:
        diff (str): diff text

    Returns:
        str: exception marker
    """
    marker_ = ""
    patterns = ["པོ་", "འི", "ཚོ་", "རིན", "\(", "\)", "།\S+", "〉", "ཏུཉེ", "ཡོཉེ"]
    for pattern in patterns:
        marker = re.search(pattern, diff)
        if marker := re.search(pattern, diff):
            marker_ += marker[0]
    return marker_


def is_punct(char):
    """Check whether char is tibetan punctuation or not.

    Args:
        diff (str): character from diff

    Returns:
        flag: true if char is punctuation false if not
    """
    if char in ["་", "།", "༔", ":", "། །"]:
        return True
    else:
        return False


def isvowel(char):
    """Check whether char is tibetan vowel or not.

    Args:
        char (str): char to be checked

    Returns:
        boolean: true for vowel and false for otherwise
    """
    flag = False
    vowels = ["\u0F74", "\u0F72", "\u0F7A", "\u0F7C"]
    for pattern in vowels:
        if re.search(pattern, char):
            flag = True
    return flag


def is_midsyl(left_diff, right_diff):
    """Check if current diff is mid syllabus.

    Args:
        left_diff (str): left diff text
        right_diff (str): right diff text

    Returns:
        boolean : True if it is mid syllabus else False
    """
    if left_diff:
        if (is_punct(left_diff[-1]) == False) and (is_punct(right_diff[0]) == False):
            return True
    return False


def handle_mid_syl(result, diffs, left_diff, i, diff, right_diff, marker_type=None):
    """Handle the middle of syllabus diff text in different situation.

    Args:
        result (list): Filtered diff list
        diffs (list): Unfilterd diff list
        left_diff (list): left diff type and text from current diff
        diff (list): current diff type and text
        i (int): current diff index
        right_diff (list): right diff type and text from current diff
        marker_type (str): marker type can be marker or candidate marker
    """
    # make it marker if marker found  (revision)
    diff_ = rm_noise(diff[1])
    if left_diff[1][-1] == " ":
        lasttwo = left_diff[1][-2:]
        result[-1][1] = result[-1][1][:-2]
        result.append([1, diff_, f"{marker_type}"])
        diffs[i + 1][1] = lasttwo + diffs[i + 1][1]
    elif right_diff[1][0] == " ":
        result.append([1, diff_, f"{marker_type}"])
    else:
        if isvowel(right_diff[1][0]):
            result[-1][1] += right_diff[1][0]
            if len(right_diff[1]) > 1:
                syls = right_diff[1].split("་")
                first_syl = syls[0][1:] + "་"
                result[-1][1] += first_syl
                diffs[i + 1][1] = diffs[i + 1][1][len(first_syl) :]
            diffs[i + 1][1] = diffs[i + 1][1][1:]
            result.append([1, diff_, f"{marker_type}"])
        else:
            lastsyl = left_diff[1].split("་")[-1]
            result[-1][1] = result[-1][1][: -len(lastsyl)]
            result.append([1, diff_, f"{marker_type}"])
            diffs[i + 1][1] = lastsyl + diffs[i + 1][1]


def handle_google_marker(diff, result):
    extras = re.sub("#", "", diff)
    if result:
        result[-1][1] += extras
    else:
        result.append([1, extras, ""])
    result.append([1, "#", "marker"])


def tseg_shifter(result, diffs, left_diff, i, right_diff):
    """Shift tseg if right diff starts with one and left diff ends with non punct.

    Args:
        result (list): filtered diff
        diffs (list): unfiltered diffs
        left_diff (list): contains left diff type and text
        i (int): current index if diff in diffs
        right_diff (list): contains right diff type and text
    """
    if right_diff[1][0] == "་" and not is_punct(left_diff[1]):
        result[-1][1] += "་"
        diffs[i + 1][1] = diffs[i + 1][1][1:]


def get_marker(diff):
    """Extarct marker from diff text.

    Args:
        diff (str): diff text

    Returns:
        str: marker
    """
    if marker := get_abs_marker(diff):
        return marker
    elif marker := get_excep_marker(diff):
        return marker
    else:
        return ""


def is_circle_number(footnote_marker):
    """Check whether footnote marker is number in circle or not and if so 
       returns equivalent number.

    Args:
        footnote_marker (str): footnote marker
    Returns:
        str: number inside the circle
    """
    value = ""
    number = re.search("[①-⑳]", footnote_marker)
    if number:
        circle_num = {
            "①": "1",
            "②": "2",
            "③": "3",
            "④": "4",
            "⑤": "5",
            "⑥": "6",
            "⑦": "7",
            "⑧": "8",
            "⑨": "9",
            "⑩": "10",
            "⑪": "11",
            "⑫": "12",
            "⑬": "13",
            "⑭": "14",
        }
        value = circle_num.get(number[0])
    return value


def translate_tib_number(footnote_marker):
    """Translate tibetan numeral in footnote marker to roman number.

    Args:
        footnote_marker (str): footnote marker
    Returns:
        str: footnote marker having numbers in roman numeral
    """
    value = ""
    if re.search("\d+\S+(\d+)", footnote_marker):
        return value
    tib_num = {
        "༠": "0",
        "༡": "1",
        "༢": "2",
        "༣": "3",
        "༤": "4",
        "༥": "5",
        "༦": "6",
        "༧": "7",
        "༨": "8",
        "༩": "9",
    }
    numbers = re.finditer("\d", footnote_marker)
    if numbers:
        for number in numbers:
            if re.search("[༠-༩]", number[0]):
                value += tib_num.get(number[0])
            else:
                value += number[0]
    return value


def get_value(footnote_marker):
    """Compute the equivalent numbers in footnote marker payload and return it.

    Args:
        footnote_marker (str): footnote marker
    Returns:
        str: numbers in footnote marker
    """
    value = ""
    if is_circle_number(footnote_marker):
        value = is_circle_number(footnote_marker)
        return value
    elif translate_tib_number(footnote_marker):
        value = translate_tib_number(footnote_marker)
        return value
    return value


def format_diff(filter_diffs_yaml_path, image_info, type_=None):
    """Format list of diff on target text.

    Args:
        diffs (list): list of diffs
        image_info (list): contains work_id, volume number and image source offset
        type_ (str): diff type can be footnote or body
    Returns:
        str: target text with transfered annotations with markers.
    """
    filtered_diffs_yaml = yaml.safe_load(filter_diffs_yaml_path.read_text(encoding="utf-8"))
    diffs = list(filtered_diffs_yaml)
    vol_num = image_info[1]
    result = ""
    for diff_type, diff_text, diff_tag in diffs:
        if diff_type == 0:
            result += diff_text
        elif diff_type == 1:
            if diff_tag:
                if diff_tag == "pedurma-pagination" and type_ == "body":
                    result += get_pg_ann(diff_text, vol_num)
                if diff_tag == "marker":
                    if marker := get_abs_marker(diff_text):
                        value = get_value(marker)
                        result += f"<{value},{marker}>"
                    elif marker := get_excep_marker(diff_text):
                        result += f"<{marker}>"
                    else:
                        result += f"<{diff_text}>"
                elif diff_tag == "page_ref":
                    result += diff_text
                elif diff_tag == "candidate-marker":
                    result += f"({diff_text})"
            else:
                result += diff_text

    return result


def reformatting_body(text):
    """Reformat marker annotation using pedurma pagination.

    Args:
        text (str): unformatted text

    Returns:
        str: formatted text
    """
    result = ""
    page_anns = re.findall("<p\S+?>", text)
    pages = re.split("<p\S+?>", text)
    for page, ann in zip_longest(pages, page_anns, fillvalue=""):
        markers = re.finditer("<.+?>", page)
        for i, marker in enumerate(markers, 1):
            repl = f"<{i},{marker[0][1:-1]}>"
            page = page.replace(marker[0], repl, 1)
        result += page + ann
    return result


def add_link(text, image_info):
    """Add link of source image page.

    Args:
        text (str): target text having footnote maker transfered
        image_info (list): contains work_id, volume number and image source offset
    Returns:
        str: target text with source image page link
    """
    result = ""

    work = image_info[0]
    vol = image_info[1]
    pref = f"I{work[1:-3]}"
    igroup = f"{pref}{783+vol}" if work == "W1PD96682" else f"{pref}{845+vol}"
    offset = image_info[2]

    lines = text.splitlines()
    for line in lines:
        # detect page numbers and convert to image url
        if re.search("<p.+?>", line):
            pg_no = re.search("<p\d+-(\d+)>", line)
            if re.search("[0-9]", pg_no.group(1)):
                if len(pg_no.group(1)) > 3:
                    pg_no = int(pg_no.group(1)[:3]) + offset
                else:
                    pg_no = int(pg_no.group(1)) + offset
                link = f"[https://www.tbrc.org/browser/ImageService?work={work}&igroup={igroup}&image={pg_no}&first=1&last=2000&fetchimg=yes]"
                result += line + "\n" + link + "\n"
            else:
                result += line + "\n"
        else:
            result += line + "\n"
    return result


def get_pagination(diff, cur_loc, diffs, vol_num):
    """Extract pedurma pagination from diffs.

    Args:
        diff (str): diff text
        cur_loc (int): current diff location in diff list
        diffs (list): diff list
        vol_num (int): volume number

    Returns:
        str: pedurma pagination
    """
    pagination = ""
    step = 0
    if diff == str(vol_num):
        for walker in diffs[cur_loc + 1 :]:
            if walker[0] == 0:
                break
            step += 1
        pagination += f"{diff}—{walker[1]}"
        del diffs[cur_loc + 1 : cur_loc + 2 + step]
    return pagination


def rm_marker(diff):
    """Remove marker of google ocr text.

    Args:
        diff (str): diff text

    Returns:
        str: diff text without footnote marker of google ocr
    """
    result = diff
    patterns = [
        "©",
        "®",
        "\“",
        "•",
        "[༠-༩]",
        "[a-zA-Z]",
        "\)",
        "\(",
        "\u0020+",
        "@",
        "་+?",
        "། །",
        "\d",
        "།",
        "༄༅",
    ]
    for pattern in patterns:
        if re.search(pattern, diff):
            result = re.sub(pattern, "", result)
    return result


def is_note(diff):
    """Check if diff text is note or marker.

    Args:
        diff (str): diff text

    Returns:
        boolean: True if diff text is note else False.
    """
    flag = True
    patterns = [
        "[①-⑳]",
        "[༠-༩]",
        "\)",
        "\(",
        "\d",
    ]
    for pattern in patterns:
        if re.search(pattern, diff):
            flag = False
    return flag


def parse_pg_ref_diff(diff, result):
    """Parse page ref and marker if both exist in one diff.

    Args:
        diff (str): diff text
        result (list): filtered diff
    """
    lines = diff.splitlines()
    for line in lines:
        if line:
            if re.search("<r.+?>", line):
                result.append([1, line, "page_ref"])
            elif marker := re.search("(<m.+?>)(.+)", line):
                result.append([1, marker.group(1), "marker"])
                result.append([1, marker.group(2), ""])
            elif marker := re.search("<m.+?>", line):
                result.append([1, marker[0], "marker"])


def reformat_footnote(text):
    """Replace edition name with their respective unique id and brings every footnote to newline.
    
    Args:
        text (str): google OCRed footnote with namsel footnote markers transfered.
    Returns:
        (str): reformatted footnote
    """
    editions = [
        ["«སྡེ་»", "«d»"],
        ["«གཡུང་»", "«y»"],
        ["«གཡུང»", "«y»"],
        ["«ལི་»", "«j»"],
        ["«པེ་»", "«q»"],
        ["«སྣར་»", "«n»"],
        ["«ཅོ་»", "«c»"],
        ["«ཁུ་»", "«u»"],
        ["«ཞོལ་»", "«h»"],
    ]
    text = text.replace("\n", "")
    text = re.sub("(<+)", r"\n\1", text)
    for edition, edition_id in editions:
        text = text.replace(edition, edition_id)
    return text


def filter_diffs(diffs_yaml_path, type, image_info):
    """Filter diff of text A and text B.

    Args:
        diffs_list (list): list of diffs
        type (str): type of text
        image_info (list): contains work_id, volume number and source image offset.

    Returns:
        list: filtered diff
    """
    left_diff = [0, ""]
    diffs_yaml = yaml.safe_load(diffs_yaml_path.read_text(encoding="utf-8"))
    result = []
    vol_num = image_info[1]
    diffs = list(diffs_yaml)
    for i, diff in enumerate(diffs):
        if diff[0] == 0:  # in B not in A
            result.append([diff[0], diff[1], ""])
        elif diff[0] == 1:
            if re.search("#", diff[1]):
                handle_google_marker(diff[1], result)
            else:
                result.append([diff[0], diff[1], ""])
        elif diff[0] == -1:  # in A not in B
            if re.search(
                f"{vol_num}་?\D་?\d+", diff[1]
            ):  # checking diff text is pagination or not
                result.append([1, diff[1], "pedurma-pagination"])
            else:
                if i > 0:  # extracting left context of current diff
                    left_diff = diffs[i - 1]
                if i < len(diffs) - 1:  # extracting right context of current diff
                    right_diff = diffs[i + 1]
                diff_ = rm_noise(diff[1])  # removes unwanted new line, space and punct
                if left_diff[0] == 0 and right_diff[0] == 0:
                    # checks if current diff text is located in middle of a syllebus
                    if is_midsyl(left_diff[1], right_diff[1],) and get_marker(diff[1]):
                        handle_mid_syl(
                            result, diffs, left_diff, i, diff, right_diff, marker_type="marker"
                        )
                    # checks if current diff text contains absolute marker or not
                    elif get_marker(diff[1]):
                        # Since cur diff is not mid syl, hence if any right diff starts with tseg will
                        # be shift to left last as there are no marker before tseg.
                        tseg_shifter(result, diffs, left_diff, i, right_diff)
                        result.append([1, diff_, "marker"])
                    # Since diff type of -1 is from namsel and till now we are not able to detect
                    # marker from cur diff, we will consider it as candidate marker.
                    elif diff_:
                        if (
                            "ང" in left_diff[1][-3:] and diff_ == "སྐེ" or diff_ == "ུ"
                        ):  # an exception case where candidate fails to be marker.
                            continue
                        # print(diffs.index(right_diff), right_diff)
                        elif is_midsyl(left_diff[1], right_diff[1]):
                            handle_mid_syl(
                                result,
                                diffs,
                                left_diff,
                                i,
                                diff,
                                right_diff,
                                marker_type="marker",
                            )

                        else:
                            tseg_shifter(result, diffs, left_diff, i, right_diff)
                            result.append([1, diff_, "marker"])
                elif right_diff[0] == 1:
                    # Check if current diff is located in middle of syllabus or not.
                    if is_midsyl(left_diff[1], right_diff[1]) and get_marker(diff[1]):
                        handle_mid_syl(
                            result, diffs, left_diff, i, diff, right_diff, marker_type="marker"
                        )
                    elif get_marker(diff[1]):
                        # Since cur diff is not mid syl, hence if any right diff starts with tseg will
                        # be shift to left last as there are no marker before tseg.
                        tseg_shifter(result, diffs, left_diff, i, right_diff)
                        result.append([1, diff_, "marker"])
                        if "#" in right_diff[1]:
                            diffs[i + 1][1] = diffs[i + 1][1].replace("#", "")
                    else:
                        if diff_ != "" and right_diff[1] in ["\n", " "]:
                            if (
                                "ང" in left_diff[1][-2:] and diff_ == "སྐེ"
                            ):  # an exception case where candidate fails to be marker.
                                continue
                            elif is_midsyl(left_diff[1], right_diff[1]):
                                handle_mid_syl(
                                    result,
                                    diffs,
                                    left_diff,
                                    i,
                                    diff,
                                    right_diff,
                                    marker_type="marker",
                                )
                            else:
                                tseg_shifter(result, diffs, left_diff, i, right_diff)
                                result.append([1, diff_, "marker"])
                                if "#" in right_diff[1]:
                                    diffs[i + 1][1] = diffs[i + 1][1].replace("#", "")
                    # if diff_ is not empty and right diff is ['\n', ' '] then make it candidate markrer

    filter_diffs = result

    return filter_diffs


def filter_footnote_diffs(diffs, vol_num):
    """Filter the diffs of google ocr output and namsel ocr output.

    Args:
        diffs (list): diff list
        vol_num (int): colume number

    Returns:
        list: filtered diff containing notes from google ocr o/p and marker from namsel ocr o/p
    """
    left_diff = [0, ""]
    result = []
    for i, diff in enumerate(diffs):
        if diff[0] == 0:
            result.append([0, diff[1], ""])
        elif diff[0] == 1:
            if clean_diff := rm_marker(diff[1]):
                result.append([1, clean_diff, ""])
        else:
            diff_ = rm_noise(diff[1])

            if i > 0:  # extracting left context of current diff
                left_diff = diffs[i - 1]
            if i < len(diffs) - 1:  # extracting right context of current diff
                right_diff = diffs[i + 1]
            if left_diff[0] == 0 and right_diff[0] == 0 and "»" != right_diff[1].strip("་"):
                if is_note(diff[1]):
                    continue
                if re.search("<p.+?>", diff[1]):  # checking diff text is pagination or not
                    result.append([1, diff[1], "pedurma-pagination"])
                elif re.search("<r.+?>", diff[1]):
                    parse_pg_ref_diff(diff[1], result)
                else:
                    result.append([1, diff_, "marker"])
            elif right_diff[0] == 1 and "»" != left_diff[1].strip("་"):
                if re.search("<p.+?>", diff[1]):  # checking diff text is pagination or not
                    result.append([1, diff[1], "pedurma-pagination"])
                elif re.search("<r.+?>", diff[1]):
                    parse_pg_ref_diff(diff[1], result)
                elif get_abs_marker(diff[1]):
                    result.append([1, diff_, "marker"])
                    diffs[i + 1][1] = re.sub("[^\n]", "", right_diff[1])
                elif get_abs_marker(right_diff[1]):
                    result.append([1, right_diff[1], "marker"])
                elif get_excep_marker(diff[1]):
                    result.append([1, diff_, "marker"])
    return result


def postprocess_footnote(footnote):
    """Save the formatted footnote to dictionary with key as page ref and value as footnote in that page.

    Args:
        footnote (str): formatted footnote

    Returns:
        dict: key as page ref and value as footnote in that page
    """
    result = []

    page_refs = re.findall("<r.+?>", footnote)
    pages = re.split("<r.+?>", footnote)[1:]

    first_ref = page_refs[0]
    table = first_ref.maketrans("༡༢༣༤༥༦༧༨༩༠", "1234567890", "<r>")
    start = int(first_ref.translate(table))
    print(start)
    for walker, (page, page_ref) in enumerate(zip_longest(pages, page_refs, fillvalue=""), start):
        markers = re.finditer("<.+?>", page)
        marker_l = []
        for i, marker in enumerate(markers, 1):
            repl = f"<{i},{marker[0][1:-1]}>"
            page = page.replace(marker[0], repl, 1)
        marker_list = [footnote.strip() for footnote in page.splitlines()]
        marker_list[0] = f"{walker:03}-{page_ref[1:-1]}"
        # Removes the noise marker without footnote
        for marker in marker_list:
            if re.search("<.+?>(.+?)", marker):
                marker_l.append(marker)
            else:
                if "<" not in marker:
                    marker_l.append(marker)
        result.append(marker_l)
        # result[f"{walker:03}-{page_ref[1:-1]}"] = marker_list[1:]
    return result


def merge_footnote_per_page(page, foot_notes):
    markers = re.finditer("<.+?>", page)
    for i, (marker, foot_note) in enumerate(zip(markers, foot_notes[1:])):
        marker_parts = marker[0][1:-1].split(",")
        body_incremental = marker_parts[0]
        body_value = marker_parts[1]
        footnote_parts = foot_note.split(">")
        footnote_incremental = footnote_parts[0].split(",")[0][1:]
        footnote_value = footnote_parts[0].split(",")[1]
        note = footnote_parts[1]
        repl = f"<{body_incremental},{body_value};{footnote_incremental},{footnote_value},{note}>"
        page = page.replace(marker[0], repl, 1)
    result = page + f"/{foot_notes[0]}/"
    return result


def merge_footnote(body_text_path, footnote_yaml_path):
    body_text = body_text_path.read_text(encoding='utf-8')
    footnotes = yaml.safe_load(footnote_yaml_path.read_text(encoding="utf-8"))
    footnotes = list(footnotes)
    pages = re.split("<p.+?>", body_text)[:-1]
    result = ""
    for i, (page, footnote) in enumerate(zip(pages, footnotes)):
        result += merge_footnote_per_page(page, footnote)
        result += page_ann[i]
    return result


def flow(N_path, G_path, text_type, image_info):
    """ - diff is computed between B and A text
        - footnotes and footnotes markers are filtered from diffs
        - they are applied to B text with markers
        - A image links are computed and added at the end of each page

    Args:
        B_path (path): path of text B (namsel)
        A_path (path): path of text A (clean)
        text_type (str): type of text can be either body or footnote
        image_info (list): Contains work_id, volume number and source image offset
    """
    N = N_path.read_text(encoding="utf-8")
    G = G_path.read_text(encoding="utf-8")
    diffs_to_yaml = partial(to_yaml, type_="diffs")  # customising to_yaml function for diff list
    filtered_diffs_to_yaml = partial(
        to_yaml, type_="filtered_diffs"
    )  # customising to_yaml function for filtered diffs list
    footnote_to_yaml = partial(to_yaml, type_="footnote")

    # Text_type can be either body of the text or footnote footnote.
    if text_type == "body":
        diffs_yaml_path = base_path / "diffs.yaml"
        filtered_diffs_yaml_path = base_path / "filtered_diffs.yaml"
        if diffs_yaml_path.is_file():
            pass
        else:
            print("Calculating diffs...")
            diffs = get_diff(N, G)
            diffs_list = list(map(list, diffs))
            diffs_to_yaml(diffs_list, base_path)
        print("Filtering diffs...")
        filtered_diffs = filter_diffs(diffs_yaml_path, "body", image_info)
        filtered_diffs_to_yaml(filtered_diffs, base_path)
        new_text = format_diff(filtered_diffs_yaml_path, image_info, type_="body")
        new_text = reformatting_body(new_text)
        # new_text = add_link(new_text, image_info)
        # new_text = rm_markers_ann(new_text)
        (base_path / f"output/result{image_info[1]}.txt").write_text(new_text, encoding="utf-8")
    elif text_type == "footnote":
        diffs_yaml_path = base_path / "diffs.yaml"
        G = rm_google_ocr_header(G)
        clean_G = preprocessGoogleNotes(G)
        clean_N = preprocessNamselNotes(N)
        if diffs_yaml_path.is_file():
            pass
        else:
            print("Calculating diffs..")
            diffs = get_diff(clean_N, clean_G)
            diffs_list = list(map(list, diffs))
            diffs_to_yaml(diffs_list, base_path)
        filtered_diffs = filter_footnote_diffs(diffs_list, image_info[1])
        filtered_diffs_to_yaml(filtered_diffs, base_path)
        new_text = format_diff(filtered_diffs, image_info, type_="footnote")
        # new_text = rm_markers_ann(new_text)
        new_text = reformat_footnote(new_text)
        formatted_yaml = postprocess_footnote(new_text)
        footnote_to_yaml(formatted_yaml, base_path)
        (base_path / "output/result.txt").write_text(new_text, encoding="utf-8")
    else:
        print("Type not found")
    body_text_path = Path("./input/body_text/output/result73.txt")
    footnote_yaml_path = Path("./input/footnote_text/footnote.yaml")
    if body_text_path.is_file() and footnote_yaml_path.is_file():
        merge_result = merge_footnote(body_text_path, footnote_yaml_path)
        new_text = add_link(merge_result, image_info)
        Path("./input/body_text/output/merge_result73.txt").write_text(
            merge_result, encoding="utf-8"
        )
    print("Done")


if __name__ == "__main__":

    # base_path = Path("./tests/durchen_test1")
    # G_path = base_path / "input" / "G.txt"
    # N_path = base_path / "input" / "N.txt"

    # base_path = Path("./tests/test4")
    # G_path = base_path / "input" / "a.txt"
    # N_path = base_path / "input" / "b.txt"

    base_path = Path("./input/footnote_text/")
    G_path = base_path / "googleOCR_text" / "73durchen-google_num.txt"
    N_path = base_path / "namselOCR_text" / "73durchen-namsel_num.txt"

    # base_path = Path("./input/body_text")
    # G_path = base_path / "input" / "73A_transfered.txt"
    # N_path = base_path / "input" / "73B.txt"

    # base_path = Path("./input/body_text")
    # G_path = base_path / "input" / "74A-nam.txt"
    # N_path = base_path / "input" / "74A-der.txt"

    # base_path = Path("./input/body_text")
    # A_path = base_path / "cleantext" / "$.txt"
    # B_path = base_path / "ocred_text" / "v073.txt"

    # only works text by text or note by note for now
    # TODO: run on whole volumes/instances by parsing the BDRC outlines to find and identify text type and get the image locations
    image_info = [
        "W1PD96682",
        73,
        16,
    ]  # [<kangyur: W1PD96682/tengyur: W1PD95844>, <volume>, <offset>]

    text_type = "footnote"

    flow(N_path, G_path, text_type, image_info)
