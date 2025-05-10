from gibberishModules.instructions import *
from gibberishModules.imports import importDefinition
from gibberishModules.variables import isVariableScope, isVariableDatatype, variableScopeStringToEnumIntDictGet, variableDataTypesStringToInt, variable
from gibberishModules.functionDefinitions import functionDefinition

class iterableFile:
    isHeaderFile = False
    index = 0
    restoredLine = line = ""
    
    def __init__(self, fileLines: list[str]):
        self.fileLines = enumerate(fileLines)
    
    def formatCurrentLine(self):
        self.line = self.line.removesuffix('\n')
        if '//' in self.line:
            self.line = self.line[:self.line.index('//')]
        self.line = self.line.strip()
        self.restoredLine = self.line
    
    def allowGetNextLine(self, allowSemicolon: bool = False, lineMustEnd: bool = False, errorMessageSemicolon: str | None =  None, errorMessageLineDoesntEnd: str | None = None) -> bool:
        if errorMessageSemicolon is None:
            errorMessageSemicolon = f"Unexpected semicolon at line {self.index+1}!"
        if errorMessageLineDoesntEnd is None:
            errorMessageLineDoesntEnd = f"Line {self.index+1} continues unexpectedly!"
        if self.line is None:
            return True
        
        try:
            if self.line == "":
                self.index, self.line = next(self.fileLines)
                while self.line.strip() == "":
                    self.index, self.line = next(self.fileLines)
                self.restoredLine = self.line
                return True

            if self.line[0] == ";":
                assert allowSemicolon, errorMessageSemicolon
                if self.line == ";":
                    self.index, self.line = next(self.fileLines)
                else:
                    self.line = self.line[1:]
                self.restoredLine = self.line
                return True
        except StopIteration:
            self.line = None
            return True
        else:
            assert not lineMustEnd, errorMessageLineDoesntEnd
            return False
    
    def getNextTerm(self):
        self.line = self.line.lstrip()
        
        if self.line == "":
            self.term = None
            return
        
        #assert self.line != "", f"Unexpected end of line on line {self.index+1}."
        
        endPosition = 0
        
        if isBracketOrDelimiter(self.line[0]):
            self.term = self.line[0]
            self.line = self.line[1:]
            return
        
        readingOperator = isOperatorChar(term:= self.line[0])
        if readingOperator:
            if (doubleterm:= self.line[:2]) in ('++', '--', '->', '==', '!=', '>=', '<=', '&&', '||', '>>', '<<'):
                self.term = doubleterm
                self.line = self.line[2:]
            else:
                self.term = term
                self.line = self.line[1:]
            return
        
        for character in self.line:
            if (isOperatorChar(character) ^ readingOperator) or character == " ":
                break
            if (isBracketOrDelimiter(character)):
                break
            endPosition += 1
        self.term = self.line[:endPosition]
        self.line = self.line[endPosition:]
        
    def readImportDefinition(self) -> importDefinition:
        assert self.term == "import", f"Unknown file parameter on line {self.index+1}: \"{self.term}\""
        self.getNextTerm()
        dataTypeString = self.term
        self.getNextTerm()
        name = self.term
        self.getNextTerm()
        assert self.term == "from", f"Expected keyword \"from\" on line {self.index+1}, instead got \"{self.term}\""
        self.getNextTerm()
        fileID = int(self.term, 0)
        self.getNextTerm()
        assert self.term == "{", f"Expected \"{{\" on line {self.index+1}, instead got \"{self.term}\""
        self.getNextTerm()
        unknown0 = int(self.term, 0)
        self.getNextTerm()
        assert self.term == "}", f"Expected \"}}\" on line {self.index+1}, instead got \"{self.term}\""
        assert self.line == '' or self.line[0] == ';', f"Line {self.index+1} continues unexpectedly!"
        return importDefinition(name, None, 0, fileID, dataTypeString, unknown0)
    
    def readFileParameter(self) -> importDefinition | int:
        self.getNextTerm()
        if self.term == "import":
            return self.readImportDefinition()
        if self.term == "offset":
            self.getNextTerm()
            return int(self.term, 0)
    
    def readVariable(self) -> variable:
        scope = None
        dataTypeString = None
        if isVariableScope(self.term):
            scope = variableScopeStringToEnumIntDictGet(self.term)
            self.getNextTerm()
        if isVariableDatatype(self.term):
            dataTypeString = self.term
            self.getNextTerm()
        name = self.term
        
        return variable(name, None, name, None, scope, dataTypeString)
    
    def readConstValue(self, enforceUnsignedInt: bool = False) -> (int | float | str | bool | None, str | None):
        #reading a string
        if self.term in ('"', "'"):
            exitCharacter = self.term
            escapingCharacter = False
            stringValue = ""
            while True:
                exitPosition = self.line.index(exitCharacter)
                sliceLine = self.line[:exitPosition]
                self.line = self.line[exitPosition + 1:]
                sliceLine = sliceLine.replace("\\\\", "\x00")
                stringValue += sliceLine
                if sliceLine and sliceLine[-1] == "\\":
                    stringValue += exitCharacter
                    continue
                break
            stringValue = stringValue.replace("\\n", "\n")
            stringValue = stringValue.replace("\\r", "\r")
            stringValue = stringValue.replace("\\t", "\t")
            stringValue = stringValue.replace("\x00", "\\")
            return stringValue, "string"
        
        #reading a boolean
        if self.term == "true":
            return True, "bool"
        if self.term == "false":
            return False, "bool"
        
        #reading "self"
        if self.term == "self":
            return "self", "me"
        
        #reading a float or int or hex
        isNumber = (self.term[0] in "0123456789.")
        if self.term == "-" and self.line[0] in "0123456789.":
           tmp = self.term
           self.getNextTerm()
           self.term = tmp + self.term
           isNumber = True
        if isNumber:
            if len(self.term) > 1 and self.term[1] == 'x':
                return int(self.term, 0), "hex"
            if "." in self.term:
                return float(self.term), "float"
            else:
                return int(self.term, 0), "int" if not enforceUnsignedInt else "hex"
        
        #not a constant (should raise Exception?)
        return None, None