from transformers import AutoTokenizer, AutoModelForCausalLM
from transformers import T5Tokenizer, T5ForConditionalGeneration
from torch.utils.data import DataLoader, Dataset
from src.util import _normalize_answer
import pytorch_lightning as pl
import json
from torch import nn

class QASDataset(Dataset):
    def __init__(self, file_path):
        super().__init__()
        self.context, self.question, self.answer = [],[], []
        with open(file_path, 'r') as f:
            data = json.load(f)
        for d in data:
            self.question.append(d['question'])
            self.context.append(d['positive_ctxs'][0]['text'])
            self.answer.append(d['answers'])

    def __len__(self):
        assert len(self.context) == len(self.question)
        assert len(self.context) == len(self.answer)
        return len(self.context)

    def __getitem__(self, i):
        return self.context[i], self.question[i], self.answer[i]



class Reader(pl.LightningModule):
    def __init__(self, args):
        super().__init__()
        self.model_name = args.model
        if "T0" not in args.model:
            self.model = AutoModelForCausalLM.from_pretrained(args.model, cache_dir="./models/")
            self.tokenizer = AutoTokenizer.from_pretrained(args.model)
            self.template = "Passage: {d}\nQuestion: {q}\nAnswer: "
        else:
            self.model = T5ForConditionalGeneration.from_pretrained("./models/T0_3B")
            self.tokenizer = T5Tokenizer.from_pretrained("./models/T0_3B")
            self.template = "Please answer the question based on the passage.\n\nPassage: {d}\n\nQuestion: {q}"
        self.batch_size = args.batch

    def forward(self, input):
        if 'T0' not in self.model_name:
            max_length = input.input_ids.shape[1]+10
        else:
            max_length = 10
        generated_ids = self.model.generate(input.input_ids, max_length=max_length,return_dict_in_generate=True, output_scores=True)
        return generated_ids


    def test_step(self, batch, batch_idx):
        texts = [self.template.format(d=d, q=q) for d,q in zip(batch[0], batch[1])]
        input = self.tokenizer(texts, padding=True, return_tensors="pt").to(self.device)
        generated_ids = self(input)
        preds = self.tokenizer.batch_decode(generated_ids.sequences, skip_special_tokens=True)
        preds = [_normalize_answer(p.split("Answer: ")[-1]) for p in preds]
        answers = [_normalize_answer(a) for a in batch[2][0]]
        acc = self._accuracy(answers, preds)
        self.log("Test_Acc", acc,batch_size=self.batch_size)


    def _accuracy(self, golds, preds):
        total = len(golds)
        cor = sum([int(g in p) for g, p in zip(golds, preds)])
        return cor/total

    def get_dataloader(self, data_path):
        dataset = QASDataset(data_path)
        return DataLoader(dataset, batch_size=int(self.batch_size))

