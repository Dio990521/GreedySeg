import torch
from tqdm import tqdm
import json
import argparse
import numpy as np
import os

from pytorch_transformers import BertConfig,  BertModel, BertTokenizer
from utils_segmentation import convert_examples_to_features, read_expamples_2
WINDOW_SIZE = 2
SEGMENT_JUMP_STEP = 2
SIMILARITY_THRESHOLD = 0.6
MAX_SEGMENT_ROUND = 6
MAX_SEQ_LENGTH = 50
MODEL_CLASSES = {
    'bert': (BertConfig,  BertModel, BertTokenizer),
}
os.environ["CUDA_VISIBLE_DEVICES"] = "0"
def similarity(A, B):
    return np.dot(A, B) / (np.linalg.norm(A) * np.linalg.norm(B))


def generate_vectors_2(model,examples,tokenizer,device):
    features = convert_examples_to_features(examples, MAX_SEQ_LENGTH, tokenizer,
                                            cls_token=tokenizer.cls_token,
                                            cls_token_segment_id=0,
                                            sep_token=tokenizer.sep_token,
                                            )

    all_input_ids = torch.tensor([f.input_ids for f in features], dtype=torch.long).to(device)
    all_input_mask = torch.tensor([f.input_mask for f in features], dtype=torch.long).to(device)
    all_segment_ids = torch.tensor([f.segment_ids for f in features], dtype=torch.long).to(device)

    vectors = model(input_ids=all_input_ids, attention_mask=all_input_mask, token_type_ids=all_segment_ids)[1]
    return vectors.cpu().detach().numpy()

def segmentation(documents):
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    config_class, model_class, tokenizer_class = MODEL_CLASSES['bert']
    config = config_class.from_pretrained(args.berttype)
    tokenizer = tokenizer_class.from_pretrained(args.berttype,do_lower_case=True)
    model = model_class.from_pretrained(args.berttype ,config=config).to(device)#, from_tf=bool('.ckpt' in args.model_name_or_path),
    model.eval()

    all_cut_list = []
    pbar = tqdm(total=len(documents))
    for document_o in documents:
        if(len(document_o)%2):
            document=document_o[1:]
        else:
            document = document_o
        cut_index=0
        cut_list = []
        while(cut_index<len(document)):
            left_sent=""
            i=0
            temp_sent = ""
            final_value=2
            final_cutpoint=len(document)-1

            if(cut_index-WINDOW_SIZE>0):
                index=WINDOW_SIZE
                while(index>0):
                    left_sent+=document[cut_index-index]
                    index-=1

            else:
                temp_index=0
                while(temp_index<cut_index):
                    left_sent+=document[temp_index]
                    temp_index+=1

            while (cut_index + i < len(document) and i < MAX_SEGMENT_ROUND):
                temp_sent+=document[cut_index+i]
                #?????????????????? or (i==0 and cut_index + i == len(document)-1) ??????final_cutpoint????????????????????? ???????????????????????????????????????????????????
                if(i%SEGMENT_JUMP_STEP==SEGMENT_JUMP_STEP-1):
                    bert_input=[]
                    right_sent=""
                    if(cut_index+i+WINDOW_SIZE<len(document)):
                        index=1
                        while(index<=WINDOW_SIZE):
                            right_sent+=document[cut_index+i+index]
                            index+=1
                    else:
                        temp_index=1
                        while(cut_index+i+temp_index<len(document)):
                            right_sent += document[cut_index + i + temp_index]
                            temp_index+=1

                    if(left_sent):
                        bert_input.append(left_sent)
                    bert_input.append(temp_sent)
                    if(right_sent):
                        bert_input.append(right_sent)
                    examples=read_expamples_2(bert_input)
                    vectors=generate_vectors_2(model,examples,tokenizer,device)
                    if(left_sent):
                        left_value=similarity(vectors[0],vectors[1])
                        right_value = similarity(vectors[1], vectors[2]) if right_sent else -1
                    else:
                        left_value=-1
                        right_value=similarity(vectors[0],vectors[1]) if right_sent else -1
                    larger_value=left_value if left_value > right_value else right_value
                    if(not left_sent and not right_sent):#???????????????????????????????????????len(document)<=MAX_SEGMENT_ROUND

                        larger_value=SIMILARITY_THRESHOLD    #??????????????????????????????????????????????????????0.8??????????????????????????????,?????????????????????????????????
                                                             #???????????????????????????
                    if(larger_value<final_value):
                        final_value=larger_value
                        final_cutpoint=cut_index + i
                i+=1
            
            cut_list.append(final_cutpoint)
            # print(final_cutpoint)
            cut_index=final_cutpoint+1
        if(len(document_o)%2):
            cut_list_new=[i+1 for i in cut_list]
        else:
            cut_list_new=cut_list
        if (len(cut_list) == 0):
            cut_list_new = [0]
        #assert cut_list_new[-1] == len(document_o) - 1

        #---------------------------dcz
        tmp = [0] * len(document_o)
        for i in cut_list_new:
            tmp[i] = 1
        tmp[-1] = 0
        all_cut_list.append(tmp)
        #---------------------------dcz
        #all_cut_list.append(cut_list_new)

        pbar.update(1)
    pbar.close()
    #with open(CUTLIST_FILE,'w') as wf:
    #     wf.write(json.dumps(all_cut_list, ensure_ascii=False))
    return all_cut_list

def document_segmentation():
    
    for dataset in ["test"]:#:["train","valid","test"]
        print("start",dataset)
        documents=[]
        #with open(args.datapath+"test"+".txt",'r', encoding="utf-8") as rf:
        with open(args.datapath,'r', encoding="utf-8") as rf:
            tmp = []
            for line in rf:
                line=line.strip()
                # print(line.split("\t"))
                
         #---------------------------dcz
                if(line and line[0] in ["0","1","2","3","4","5","6","7"]):
                    #if(args.lan=="ch"):
                    #    document=[]
                    #    for utt in line.split("\t")[1:-1]:
                    #        document.append(''.join(utt.split(" ")))
                    #else:
                    tmp.append(line[2:])
                    #document=line.split("\t")[1:-1]
                    #documents.append(document)
                else:
                    if len(tmp) == 0: continue
                    documents.append(tmp)
                    tmp = []
        documents.append(tmp)
        #---------------------------dcz

        print("len of documents", len(documents))

        all_cut_list=segmentation(documents)
        with open("cutlist_greedySeg.json", 'w') as wf:
            wf.write(json.dumps(all_cut_list, ensure_ascii=False))


parser = argparse.ArgumentParser()
parser.add_argument("--lan",
                    default='en',
                    type=str,
                    help="The language of dataset")
parser.add_argument("--datapath",
                    default='data/alime/',
                    type=str,
                    help="The path of dataset")
parser.add_argument("--berttype",
                    default='bert-base-uncased',
                    type=str,
                    help="The type of BERT")
args = parser.parse_args()


if __name__ == '__main__':
    document_segmentation()