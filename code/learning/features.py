""" Timex patterns and pattern matching code taken from https://bitbucket.org/qwaider/textpro-en/src/fd203d54b184f2b1a5d43c7dee5aad131dce9280/FBK-timepro/resources/english-rules-temporal-markers?at=master
"""

import copy
import re
import re_timex_pattern
import nominalization
import english_rules
import negdetect

from code.notes.utilities.add_discourse import get_temporal_discourse_connectives


# these were extracted from the TimeBank corpus, and have been hardcoded here for convenience
temporal_signals = [['in'],      ['on'],                  ['after'],       ['since'],
                    ['until'],   ['in', 'advance', 'of'], ['before'],      ['to'],
                    ['at'],      ['during'],              ['ahead', 'of'], ['of'], ['by'],
                    ['between'], ['as', 'of'],            ['from'],        ['as', 'early', 'as'],
                    ['for'],     ['around'],              ['over'],        ['prior', 'to'],
                    ['when'],    ['should'],              ['within'],      ['while']]


def get_window_features(index, features_in_sentence):

    # TODO: figure out how I am going to get this to be efficient.
    # TODO: should i add null values if there are no left or right features?

    window = 4

    window_features = {}

    left_start    = max(index - window, 0)
    left_end      = index

    right_start   = index + 1
    right_end     = index + window + 1

    left_features  = {("left_{}_{}".format(i, key), f[key]):True for i, f in enumerate(features_in_sentence[left_start:left_end]) for key in f}
    right_features = {("right_{}_{}".format(i, key), f[key]):True for i, f in enumerate(features_in_sentence[right_start:right_end]) for key in f}

    window_features.update(left_features)
    window_features.update(right_features)

    return window_features


def get_preceding_labels(token, labels):

    """Get the IOB labeling of the previous 4 tokens.
    """

    features = {}
    preceding_labels = []

    window = 4

    start = max(token["token_offset"] - window, 0)
    end   = token["token_offset"]

    if len(labels) > 0:

        # iob label for token
        preceding_labels = [l["entity_label"] for l in labels[token["sentence_num"] - 1][start:end]]

        # normalize the features
        if token["token_offset"] - window < 0:
            preceding_labels = ((['O'] * abs(token["token_offset"] - window)) + preceding_labels)

    else:
        preceding_labels = ['O']*4

    assert len(preceding_labels) == 4, "preceding _labels: {}".format(preceding_labels)

    for i, l in enumerate(preceding_labels):
        features[("preceding_labels_{}".format(i), l)] = 1

    return features

def extract_tlink_features(note):
    tlink_features = []

    for tlink_pair in note.get_tlinked_entities():

        pair_features = {}

        # entities. timexes may be composed of multiple tokens
        target_tokens = tlink_pair['target_entity']
        source_tokens = tlink_pair['src_entity']

        tokens = []
        target_pos_tags = set()

        for i, target_token in enumerate(target_tokens):

            text_feature = get_text(target_token,"target_token_{}".format(i))
            tokens.append(text_feature.keys()[0][1])
            pair_features.update(text_feature)
            pair_features.update(get_lemma(target_token,"target_lemma_{}".format(i)))

            target_pos_feature = get_pos_tag(target_token,"target_pos_{}".format(i))
            target_pos_tags.add(target_pos_feature.keys()[0][1])
            pair_features.update(target_pos_feature)

            pass

        chunk = " ".join(tokens)
        pair_features.update({("target_chunk",chunk):1})

        tokens = []
        src_pos_tags = set()

        for i, source_token in enumerate(source_tokens):

            text_feature = get_text(source_token,"src_token_{}".format(i))
            tokens.append(text_feature.keys()[0][1])
            pair_features.update(text_feature)
            pair_features.update(get_lemma(source_token,"src_lemma_{}".format(i)))
            src_pos_feature = get_pos_tag(target_token,"src_pos_{}".format(i))
            src_pos_tags.add(src_pos_feature.keys()[0][1])
            pair_features.update(src_pos_feature)

            pass

        chunk = " ".join(tokens)
        pair_features.update({("src_chunk",chunk):1})
        pair_features.update({("same_pos", None):(src_pos_tags == target_pos_tags)})
        pair_features.update(get_sentence_distance(source_tokens, target_tokens))
        pair_features.update(get_num_inbetween_entities(source_tokens,target_tokens, note))
        pair_features.update(doc_creation_time_in_pair(source_tokens,target_tokens))
        pair_features.update(get_discourse_connectives_pair_features(source_tokens,target_tokens, note))
        pair_features.update(get_temporal_signal_features(source_tokens,target_tokens,note))

        tlink_features.append(pair_features)

    return tlink_features

def _entity_type_entity(entity, note):
    # doc time
    if 'functionInDocument' in entity[0]:
        return "TIMEX"
    return note.get_labels()[entity[0]["sentence_num"]-1][entity[0]["token_offset"]]["entity_type"]

def get_discourse_connectives_pair_features(src_entity, target_entity, note):
    """
    return tokens of temporal discourse connectives and their distance from each entity, if connective exist and entities are on the same line.
    """

    # if both entities are not events, return
    if _entity_type_entity(src_entity, note) != "EVENT" or _entity_type_entity(target_entity,note) != "EVENT":
        return {}

    # extract relevent attributes from entities
    # only concider token [0] in entity because events only have 1 token
    src_line_no     = src_entity[0]["sentence_num"]
    src_offset      = src_entity[0]["token_offset"]
    target_line_no  = target_entity[0]["sentence_num"]
    target_offset   = target_entity[0]["token_offset"]

    # connectives are only obtained for single sentences, and connot be processed for pairs that cross sentence boundaries
    if src_line_no != target_line_no or src_line_no is None or target_line_no is None:
        return {}

    # get discourse connectives.
    connectives = get_discourse_connectives(src_line_no, note)

    # if there are no connectives
    if connectives == []:
        return {}

    connective_feats = {}
    connective_id = None
    connective_tokens = ''
    connective_pos = None

    for connective_token in connectives:

        # find connective position relative to entities
        if src_offset < connective_token["token_offset"] and connective_token["token_offset"] < target_offset:
            connective_pos = "connective_between"
        elif target_offset < connective_token["token_offset"] and connective_token["token_offset"] < src_offset:
            connective_pos = "connective_between"

        elif src_offset < target_offset and target_offset < connective_token["token_offset"]:
            connective_pos = "connective_after"
        elif target_offset < src_offset and src_offset < connective_token["token_offset"]:
            connective_pos = "connective_after"

        elif connective_token["token_offset"] < src_offset and src_offset < target_offset:
            connective_pos = "connective_before"
        elif connective_token["token_offset"] < target_offset and target_offset < src_offset:
            connective_pos = "connective_before"

        elif connective_token["token_offset"] == src_offset:
            connective_pos = "connective_is_src"
        elif connective_token["token_offset"] == target_offset:
            connective_pos = "connective_is_target"

        # sanity check
        assert connective_pos is not None

        # add connective to features list
        # assert (connective_pos, connective_token["token"]) not in connective_feats
        connective_feats.update({(connective_pos, connective_token["token"]):1})

    # return feature dict
    return connective_feats

def get_discourse_connectives_event_features(token, note):
    """
    return rather or not the token in question is part of a temporal discourse connective
    """

    line_no = token["sentence_num"]

    # get discourse connectives.
    connectives = get_discourse_connectives(line_no, note)

    # check if token is part of a connective
    for connective_token in connectives:
        if token["token"] == connective_token["token"] and token["token_offset"] == connective_token["token_offset"]:
            return {"is_discourse_connective":1}

    return {"is_discourse_connective":0}

def get_discourse_connectives(line_no, note):
    '''get discourse connectives for the given line'''

    connectives = []

    # check if the connectives have been caches. if they haven't, extract and cache them
    note_connectives = note.get_discourse_connectives()
    if line_no in note_connectives:
        connectives = note_connectives[line_no]
    else:
        constituency_tree = note.get_sentence_features()[line_no]['constituency_tree']
        connectives = get_temporal_discourse_connectives(constituency_tree)
        note.add_discourse_connectives({line_no:connectives})

    return connectives


def doc_creation_time_in_pair(src_entity, target_entity):

    feature = {("doctimeinpairm",None):0}

    if 'functionInDocument' in src_entity[0]:
        if src_entity[0]['functionInDocument'] == 'CREATION_TIME':
            feature = {("doctimeinpair",None):1}
    if 'functionInDocument' in target_entity[0]:
        if target_entity[0]['functionInDocument'] == 'CREATION_TIME':
            feature = {("doctimeinpair",None):1}

    return feature

def get_num_inbetween_entities(src_entity, target_entity, note):

    """
    possible situations:

        EVENT -> all following EVENTs in same sentence

        EVENT -> all following TIMEX  in same sentence

        TIMEX -> all following EVENTS in same sentence

        main verb EVENTS in sentence -> main verb EVENTS in following sentence, if there is one.
    """

    # start of entity?
    start_of_entity = lambda label: "I_" not in label and label != "O"

    entity_count = 0

    iob_labels = note.get_labels()

    # doctime does not have a position within the text.
    if "sentence_num" not in src_entity[0] or "sentence_num" not in target_entity[0]:
        return {("entity_distance",None):-1}

    # this proj has poorly managed indexing. bad coding practice. SUE ME!
    # get the sentence index of entities
    src_sentence    = src_entity[0]["sentence_num"] - 1
    target_sentence = target_entity[0]["sentence_num"] - 1

    # entities are in adjacent sentences
    if src_sentence != target_sentence:

        # want to get distance between end and start of tokens
        end_src_token      = src_entity[-1]["token_offset"]
        start_target_token = target_entity[0]["token_offset"]

        # get iob labels. concatenate and then find all labels that are not I_ or O
        chunk1 = iob_labels[src_sentence][end_src_token+1:]
        chunk2 = iob_labels[target_sentence][:start_target_token]

        labels = chunk1 + chunk2

        # count all labels with B_ (TIMEX) or not O (EVENT)
        for label in labels:
            if start_of_entity(label):
                entity_count += 1

    # tokens must be in same sentence
    else:

        # we need to check if src or target entity is a EVENT or TIMEX
        # because of the way TEA pairs stuff, I (kevin) always made EVENTS come first within
        # a pairing event if the EVENT came after a TIMEX. I did this because I just did a literal
        # translation from the paper we were following.

        # same sentence.
        sentence_num = src_sentence

        # if end of src comes before start of target just find the number of entities between
        # otherwise if end comes after just take distance between last index of target and first index of src

        end_src_token       = src_entity[-1]["token_offset"]
        start_target_token  = target_entity[0]["token_offset"]

        start_src_token     = src_entity[0]["token_offset"]
        end_target_token    = target_entity[-1]["token_offset"]

        sentence_labels = iob_labels[sentence_num]
        labels          = None

        if end_src_token < start_target_token:
            labels = sentence_labels[end_src_token+1:start_target_token]
        else:
            labels = sentence_labels[end_target_token+1:start_src_token]

        for label in labels:
            if start_of_entity(label):
                entity_count += 1

    return {("entity_distance",None): entity_count}

def get_sentence_distance(src_entity, target_entity):
    """
    Sentence distance (e.g. 0 if e1 and e2 are in the same sentence)
    Since we only consider pairs of entities within same sentence or adjacent
    it must be 0 or 1
    """

    # assuming each entity's tokens are all in the same sentence.

    sentence_dist_feat = {("sent_distance",None):-1}

    # if doctime occurs then there is no distance since it is not in a sentence.
    if 'sentence_num' in src_entity[0] and 'sentence_num' in target_entity[0]:
        src_line_no    = src_entity[0]["sentence_num"]
        target_line_no = target_entity[0]["sentence_num"]

        sentence_dist_feat = {("sent_distance",None):abs(src_line_no - target_line_no)}

    return sentence_dist_feat


def extract_event_feature_set(note, labels, predict=False, timexLabels=None):
    return extract_iob_features(note, labels, "EVENT", predicting=predict, timexLabels=timexLabels)


def extract_timex_feature_set(note, labels, predict=False):
    return extract_iob_features(note, labels, "TIMEX3", predicting=predict)


def extract_event_class_feature_set(note, labels, eventLabels, predict=False, timexLabels=None):
    return extract_iob_features(note, labels, "EVENT_CLASS", predicting=predict, eventLabels=eventLabels, timexLabels=timexLabels)


def update_features(token, token_features, labels):
    """ needed when predicting """
    token_features.update(get_preceding_labels(token, labels))


def extract_iob_features(note, labels, feature_set, predicting=False, eventLabels=None, timexLabels=None):

    """ returns featurized representation of events and timexes """

    features = []

    tokenized_text = note.get_tokenized_text()

    preceding_features = []

    for line in tokenized_text:

        for token in tokenized_text[line]:

            token_features = {}

            # get features specific to a specific label type
            if feature_set == "TIMEX3":
                token_features.update(get_lemma(token))
                token_features.update(get_text(token))
                token_features.update(get_chunk(token))
                token_features.update(get_pos_tag(token))
                token_features.update(get_morpho_pos_tag(token))
                token_features.update(get_ner_features(token))
                token_features.update(timex_regex_feats(token))
            elif feature_set == "EVENT":
                token_features.update(get_lemma(token))

                token_features.update(get_morpho_pos_tag(token))
                token_features.update(get_pos_tag(token))

                token_features.update(is_timex(token, timexLabels))
                token_features.update(is_ner(token))

                token_features.update(get_tense(token, note.id_to_tok))
                token_features.update(is_negated(token, tokenized_text))

                token_features.update(is_predicate(token))
                token_features.update(is_coreferenced(token))
                token_features.update(is_nominalization(token))
            elif feature_set == "EVENT_CLASS":
                token_features.update(get_lemma(token))

                token_features.update(get_morpho_pos_tag(token))
                token_features.update(get_pos_tag(token))

                token_features.update(is_timex(token, timexLabels))
                token_features.update(is_ner(token))

                token_features.update(get_tense(token, note.id_to_tok))
                token_features.update(is_negated(token, tokenized_text))

                token_features.update(is_predicate(token))
                token_features.update(is_coreferenced(token))
                token_features.update(is_nominalization(token))

                token_features.update(get_chunk(token))
                token_features.update(get_discourse_connectives_event_features(token, note))
                token_features.update(is_main_verb(token))
                token_features.update(semantic_roles(token))
                token_features.update(is_event(token, eventLabels))
                token_features.update(predicate_tokens(token))
            else:
                raise Exception("ERROR: invalid feature set")

            feature_copy = copy.deepcopy(token_features)

            # labels are meaningless when this function is called when predicting, don't know the labels yet.
            if not predicting:
                token_features.update(get_preceding_labels(token, labels))

            # get the features of the 4 previous tokens.
            # TODO: might be a problem later on, in terms of performance?
            for i, f in enumerate(preceding_features):
                for key in f:
                    token_features[("preceding_feats_{}_{}".format(i, key[0]), key[1])] = f[key]

            if len(preceding_features) < 4:
                preceding_features.append(feature_copy)
            else:
                preceding_features.pop(0)

            features.append(token_features)

    # get features of following 4 tokens:
    for i, token_features in enumerate(features):
        following = features[i + 1:i + 5]
        for j, f in enumerate(following):
            for key in f:
                if ("preceding_feats_" in key[0]) or ("preceding_labels_" in key[0]):
                    continue

                token_features[("following_{}_{}".format(j, key[0]), key[1])] = f[key]

    return features

def is_predicate(token):
    f = {("is_predicate",None):0}

    if "is_predicate" in token:
        f = {("is_predicate",None):1 if token["is_predicate"] else 0}

    """
    print
    print token
    print f
    print
    """

    return f


def predicate_tokens(token):

    f = {}

    if "predicate_tokens" in token:
        for predicate_token in token["predicate_tokens"]:
            f[("predicate_token",predicate_token)] = 1
    else:
        f[("predicate_token","NULL")] = 1

    return f


def semantic_roles(token):
    feats = {}
    if "semantic_roles" in token:
        for role in token["semantic_roles"]:
            feats.update({("semantic_role",role):1})

    """
    print
    print token
    print feats
    print
    """

    return feats

def is_main_verb(token):
    feat = {("main_verb",None):0}
    if "is_main_verb" in token:
        feat = {("main_verb",None):1 if token["is_main_verb"] else 0}

    """
    print
    print token
    print feat
    print
    """

    return feat


def is_event(token, eventLabels):

    f = {("is_event", None):(eventLabels[token["sentence_num"]-1][token["token_offset"]]["entity_label"] == "EVENT")}

    """
    print
    print token
    print eventLabels[token["sentence_num"]-1][token["token_offset"]]["entity_label"]
    print f
    print
    """

    return f

def is_ner(token):

    f = {("is_ner", None):0}

    #print
    #print token["ner_tag"]
    #print token["ne_chunk"]

    if token.get("ner_tag", "NONE") != 'NONE' and token.get("ne_chunk", 'NULL') != 'NULL':
        f = {("is_ner", None):1}

    #print f
    #print

    return f

def get_chunk(token):

    f = None

    if token.get("ne_chunk", "NULL") != "NULL":
        f = {("chunk", token["ne_chunk"]):1}
    else:
        f = {("chunk", token["token"] if "token" in token else "DATE"):1}

    # print f
    return f

def get_ner_features(token):

    f = {}

    if "ner_tag" in token:
        f = {("ner_tag", token["ner_tag"]):1,
             ("ne_chunk", token["ne_chunk"]):1}

    return f

def get_text(token,feat_name="text"):

    #print
    #print token
    #print

    if "token" in token:
        return {(feat_name,token["token"]):1}
    else:
        return {(feat_name, "DATE"):1}


def get_pos_tag(token,feat_name="pos_tag"):

    if "pos" in token:
        return {(feat_name, token["pos"]):1}
    else:
        # creation time.
        return {(feat_name, "DATE"):1}

def get_morpho_pos_tag(token, feat_name="morpho_pos_tag"):

    if "morpho_pos" in token:
        return {(feat_name, token["morpho_pos"]):1}
    else:
        return {(feat_name, "DATE"):1}


def get_lemma(token,feat_name="lemma"):

    if "pos_tag" in token:
        return {(feat_name, token["lemma"]):1}
    else:
        # creation time
        # TODO: make better?
        return {(feat_name, "DATE"):1}

def get_temporal_signal_features(src_entity, target_entity, note):

    # doc time in pair. not same sentence.
    if "sentence_num" not in src_entity[0] or "sentence_num" not in target_entity[0]:
        return {}

    # extract relevent attributes from entities
    src_line_no      = src_entity[0]["sentence_num"]
    src_start_offset = src_entity[0]["token_offset"]
    src_end_offset   = src_entity[-1]["token_offset"]

    target_line_no       = target_entity[0]["sentence_num"]
    target_start_offset = target_entity[0]["token_offset"]
    target_end_offset   = target_entity[-1]["token_offset"]

    # signals are currently only examined for pairs in the same sentence
    if src_line_no != target_line_no or src_line_no is None or target_line_no is None:
        return {}

    # get signals in sentence
    signals = get_temporal_signals_in_sentence(src_line_no, note)
    retval = {}

    # extract positional features for each signal
    for signal in signals:
        signal_text = signal['tokens']
        retval.update({(signal_text + '_signal'):1})
        if signal['end'] < src_start_offset:
            retval.update({(signal_text + "_signal_before_src"): 1})
        if src_end_offset < signal['start']:
            retval.update({(signal_text + "_signal_after_src"): 1})
        if signal['end'] < target_start_offset:
            retval.update({(signal_text + "_signal_before_target"): 1})
        if target_end_offset < signal['start']:
            retval.update({(signal_text + "_signal_after_target"): 1})

    return retval

def get_temporal_signals_in_sentence(line_no, note):

    # get sentence in question
    sentence = note.get_tokenized_text()[line_no]
    signals = []

    # for every token, see if it is in every signal
    for i, token in enumerate(sentence):
        for signal in temporal_signals:
            token_is_signal = True
            signal_text = ""

            # check if the whole signal is present
            signal_end = i
            for j in range(len(signal)):
                if sentence[i+j]['token'] != signal[j]:
                    token_is_signal = False
                    break
                signal_text += signal[j] + ' '
                signal_end = i + j

            # if signal is present, do shit
            if token_is_signal:
                signals.append({"start": i, "end": signal_end, "tokens": signal_text})
                break

    return signals


def timex_regex_feats(token):

    timex = None

    if "token" in token:
        timex = token["token"]
    else:
        timex = token["value"]

    feats =  {("_YY_",None): 0,
              ("_TIME_", None): 0,
              ("_DURATION_", None): 0,
              ("_NUMBER_", None): 0,
              ("_OTHER_", None): 0,
              ("_UNIT_", None): 0,
              ("_DAY_", None): 0,
              ("_MONTH_", None): 0,
              ("_SEASON_", None): 0,
              ("_ON_", None): 0,
              ("_PD_", None): 0,
              ("_CN_", None): 0,
              ("_AVT_", None): 0,
              ("_NAMES_", None): 0,
              ("_SET_", None): 0,
              ("_", None): 0}

    # contains digits
    if re.search("[0-9]", timex):

        patterns = [re_timex_pattern.yy, re_timex_pattern.time, re_timex_pattern.duration, re_timex_pattern.number]
        keys = [("_YY_", None), ( "_TIME_", None), ("_DURATION_", None),  ("_NUMBER_", None)]

        for key, pattern in zip(keys, patterns):
            if re.search(pattern, timex):
                feats[key] = 1
                break
        else:
            feats[("_OTHER_", None)] = 1

    # doesn't dontain digits.
    else:

        keys =  [("_UNIT_", None), ("_DAY_", None), ("_MONTH_", None), ("_SEASON_", None), ("_ON_", None),
                 ("_PD_", None), ("_CN_", None), ("_AVT_", None), ("_NAMES_", None), ("_SET_", None)]

        patterns = [re_timex_pattern.unit, re_timex_pattern.day, re_timex_pattern.month, re_timex_pattern.season, re_timex_pattern.ordinal_number,
                    re_timex_pattern.parts_of_the_day, re_timex_pattern.cardinal_number, re_timex_pattern.adverbs, re_timex_pattern.names, re_timex_pattern.set_pattern]

        for key, pattern in zip(keys, patterns):
            if re.search(pattern, timex):
                feats[key] = 1
                break
        else:
            feats[("_", None)] = 1

    return feats

def is_nominalization(token):
    feat = {("is_nominalization",None):0}

    if "token" in token:
        if token["token"] in nominalization.nominalization_list:
            feat = {("is_nominalization",None):1}

    return feat

def get_tense(token, id_to_tok):

#    print "getting tense aspect features"

#    print "TOKEN: ", token["token"]

    tense, _ = english_rules.get_tense_aspect(token)

#    print "TENSE: ", tense

    return {("tense",tense):1}

def is_coreferenced(token):

    f = {("is_corferenced", None):0}

    if "coref_chain" in token:
        if token["coref_chain"] != "None":
            f = {("is_corferenced", None):1}

    #print f

    return f

def is_negated(token, text):
    sentence = [t["token"] for t in text[token["sentence_num"]]]
    # assume that default polarity is POSITIVE (0). if negation becomes NEGATIVE (1)
    f = {("negated",None):negdetect.is_negated(sentence, token["token"])}
    #print
    #print token["token"]
    #print sentence
    #print f
    #print
    return f

def is_timex(token, timexLabels):

    f = {("is_timex", None):1 if timexLabels[token["sentence_num"]-1][token["token_offset"]]["entity_label"] != 'O' else 0}

#    print
#    print timexLabels[token["sentence_num"]-1][token["token_offset"]]
#    print f
#    print

    return f

