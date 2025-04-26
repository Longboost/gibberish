from dataclasses import dataclass
@dataclass
class rawWord:
    index: int
    value: int

def getNextWord(wordsEnumerated: enumerate, currentWord: rawWord):
    currentWord.index, currentWord.value = next(wordsEnumerated)