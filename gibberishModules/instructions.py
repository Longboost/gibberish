from collections.abc import Callable
from typing import Generator
from struct import pack, unpack
from gibberishModules.words import *
from gibberishModules.functionDefinitions import *
from gibberishModules.imports import *
from gibberishModules.variables import *
from gibberishModules.arrays import *

indentLevel = 0
indentOffsetNextLine = 0
currentFunctionTree = list()
variableIDsDefinedInCpp = set()
maxInstructionID = 0xa0
def setMaxInstructionID(value: int):
    global maxInstructionID
    maxInstructionID = value

#[parent]
#the superclass all instructions inherit from
class parentInstruction:
    instructionID = 0x0
    disableExpression = False
    
    def __init__(self, instructionID: int | None = None, disableExpression: bool = False):
        if instructionID is None:
            self.instructionID = invertedInstructionDict[type(self)]
        else:
            self.instructionID = instructionID
        
        self.disableExpression = disableExpression
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        # it's fine for an instruction to not have this defined, just do nothing
        pass
    
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        raise Exception(f"Instruction {hex(self.instructionID)} ({self.__name__}) missing writeToCpp definition.")
        
    def readFromCpp(self, file: object, thisData: object):
        # it's fine for an instruction to not have this defined, just do nothing
        pass
    
    def writeToKsm(self, section: object):
        finalIdentifier = self.instructionID | (self.disableExpression << 8)
        section.words.append(finalIdentifier)
    
    def writeToKsmAfter(self, section: object):
        # it's fine for an instruction to not have this defined, just do nothing
        pass

#this is not an instruction, but rather a list of instructions on a single line i.e.:
#
#int x = 5 + 4;
#       ┕--┬--┛
#       "5 + 4" would be an expression
#
#...just think of what expressions are in maths... basically that :)
class expression:
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        cppText = " ".join(instruction.writeToCpp(indentLevel)[0].removesuffix(';\n') for instruction in self.instructions)
        return cppText, indentLevel, 0
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        self.instructions = []
        while True:
            try:
                getNextWord(wordsEnumerated, currentWord)
            except StopIteration:
                break
            newInstruction = matchInstruction(currentWord.value, True)(currentWord.value, False)
            if isinstance(newInstruction, closeExpressionInstruction) or isinstance(newInstruction, closeCallArgumentsInstruction):
                break
            newInstruction.readFromKsm(wordsEnumerated, currentWord)
            self.instructions.append(newInstruction)
    
    def readFromCpp(self, file: object, thisData: object, exitingCharacters: str | list[str], enforceUnsignedInt: bool = False) -> str:
        def readAnyValue() -> parentInstruction:
            if file.term == "accumulator":
                return thisData.generateVariableInstruction(thisData.getAccumulator())
            
            matchedImport = thisData.definedImports.get(file.term, None)
            if not matchedImport is None:
                if not matchedImport in thisData.usedImportSlots:
                    thisData.usedImportSlots.append(matchedImport)
                    matchedImport.identifier = len(thisData.usedImportSlots) + maxInstructionID
                matchedImport.timesUsed += 1
                return importedInstruction(matchedImport.identifier, False)
            
            constValue, dataTypeString = file.readConstValue(enforceUnsignedInt)
            if not constValue is None:
                return thisData.generateVariableInstruction(thisData.getConst(constValue, dataTypeString))
            
            matchedOperator = getOperatorIdentifier(file.term)
            if not matchedOperator is None:
                return operatorInstruction(matchedOperator, False)
            
            if (matchedArray := thisData.definedGlobalArrays.get(file.term)) is not None or (thisData.localDefinedArraysTree and (matchedArray := thisData.localDefinedArraysTree[-1].get(file.term)) is not None):
                tempRefVar = variable(matchedArray.name, None, matchedArray.name, None, variableScope.static, "func")
                return thisData.generateVariableInstruction(tempRefVar)
            
            matchedVariable = file.readVariable()
            matchedVariable = thisData.handleVariable(matchedVariable)
            return thisData.generateVariableInstruction(matchedVariable)
        
        self.instructions = list()
        while not (
                (file.term is None and (';' in exitingCharacters or '{' in exitingCharacters)) or
                file.term in exitingCharacters
                ):
            if type(newInstruction := identifyInstructionFromCpp(file, thisData, True)) == callInstruction:
                newInstruction.readFromCpp(file, thisData, True)
            else:
                newInstruction = readAnyValue()
                file.getNextTerm()
            self.instructions.append(newInstruction)
        if file.term is None: file.term = ';'
        return file.term
    
    def writeToKsm(self, section: object):
        for instruction in self.instructions:
            instruction.writeToKsm(section)
        closeExpressionInstruction().writeToKsm(section)

#N/A
#this is to catch any unknown instructions
class unknownInstruction(parentInstruction):
    def __init__(self, instructionID: int | None = None, disableExpression: bool = False):
        parentInstruction.__init__(self, instructionID, disableExpression)
        #print(f"Warning: initialising unknownInstruction {hex(instructionID)}, disableExpression={disableExpression}")
    
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        return f"?{hex(self.instructionID)};\n", indentLevel, 0

#0x01
#End File - marks the end of the file
class endFileInstruction(unknownInstruction):
    pass

#0x02
#Noop - does nothing, but does not get compiled away. 
class noopInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        return "noop;\n", indentLevel, 0
    
    def readFromCpp(self, file: object, thisData: object):
        file.allowGetNextLine(True, True)

#0x03
#Return - exits the function, returning a value to the caller
class returnInstruction(parentInstruction):
    returnValue = None
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        if self.returnValue is None:
            return f"return{'*' if self.disableExpression else ''};\n", indentLevel, 0
        else:
            return f"return{'*' if self.disableExpression else ''} {self.returnValue.writeToCpp(indentLevel)[0]};\n", indentLevel, 0
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        self.returnValue = readPotentialExpression(wordsEnumerated, currentWord, self.disableExpression)
    
    def readFromCpp(self, file: object, thisData: object):
        assert file.term == "return"
        file.getNextTerm()
        if file.term == '*':
            self.disableExpression = True
            thisData.allowDisableExpression = True
            if file.allowGetNextLine(True, False):
                self.returnValue = expression()
                self.returnValue.instructions = list()
                return
            file.getNextTerm()
        self.returnValue = expression()
        self.returnValue.readFromCpp(file, thisData, ';')
        if self.disableExpression:
            assert len(self.returnValue.instructions) == 1
            self.returnValue = self.returnValue.instructions[0]
        file.allowGetNextLine(True, True)
        
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.returnValue.writeToKsm(section)

#0x04
#Label - Used by GoTos to jump other parts of a function 
class labelInstruction(parentInstruction):
    alias = "undefLabel"
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        return f"{self.alias}:\n", indentLevel, 0
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        assert not self.disableExpression
        linkedLabelDefinition = currentFunctionTree[-1].labelsByAddress.get(currentWord.index, None)
        self.alias = linkedLabelDefinition.alias
    
    def readFromCpp(self, file: object, thisData: object):
        name = file.term
        self.label = thisData.declaredLabelStack[-1].get(name, None)
        if self.label is None:
            self.label = label(None, None, name)
        else:
            thisData.declaredLabelStack[-1].pop(name)
        thisData.declaredLabelStack[-1][name] = self.label
        identifier = len(thisData.usedIdentifierSlots) + thisData.identifierSlotOffset
        self.label.identifier = identifier
        thisData.usedIdentifierSlots.append(self.label)
        if thisData.functionTree[-1].specialLabel == name:
            thisData.functionTree[-1].specialLabel = self.label
        file.getNextTerm()
        assert file.term == ':'
        file.allowGetNextLine(False, False)
    
    def writeToKsm(self, section: object):
        self.label.address = len(section.words) 
        super().writeToKsm(section)

#0x05
#OpenFunction - The start of a function
#details of a function's definition are stored in another section
class openFunctionInstruction(parentInstruction):
    name = "undefFunction"
    unknown = 0x00000000
    isPublic = False
    specialLabelAlias = None
    
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        indentOffsetNextLine = 1
        accessSpecifier = "public" if self.isPublic else "private"
        
        argumentsText = ', '.join(argument.writeToCpp(indentLevel)[0].removesuffix(';\n') for argument in self.arguments)
        
        
        cppText = f"{accessSpecifier} {self.name}({argumentsText}) {'-> ' + self.specialLabelAlias if not self.specialLabelAlias is None else ''} {{\n"
        
        return cppText, indentLevel, indentOffsetNextLine
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        assert not self.disableExpression
        # function id - use to link to appropiate function definition
        getNextWord(wordsEnumerated, currentWord)
        
        linkedFunctionDefinition = functionDefinitionDictGet(currentWord.value)
        if not linkedFunctionDefinition is None:
            self.name = linkedFunctionDefinition.name
            self.isPublic = linkedFunctionDefinition.isPublic
            if not linkedFunctionDefinition.specialLabel is None:
                self.specialLabelAlias = linkedFunctionDefinition.specialLabel.alias
        else:
            raise Exception(f"{hex(currentWord.value,)}, {hex(currentWord.index * 4)}")
        global currentFunctionTree
        currentFunctionTree.append(linkedFunctionDefinition)
        
        self.arguments = []
        while True:
            getNextWord(wordsEnumerated, currentWord)
            newArgument = matchInstruction(currentWord.value)(currentWord.value, False)
            if isinstance(newArgument, closeFunctionArgumentsInstruction):
                break
            newArgument.readFromKsm(wordsEnumerated, currentWord)
            self.arguments.append(newArgument)
    
    def readFromCpp(self, file: object, thisData: object):
        thisData.localDefinedVariablesTree.append(dict())
        thisData.localDefinedArraysTree.append(dict())
        thisData.localDefinedGlobalFlagsTree.append(dict())
        thisData.bracesTree.append(self)
        thisData.declaredLabelStack.append(dict())
        isPublic = (file.term == "public")
        file.getNextTerm()
        name = file.term
        self.function = thisData.definedFunctions.get(name, None)
        identifier = len(thisData.usedIdentifierSlots) + thisData.identifierSlotOffset
        duplicate = False
        if self.function is None:
            self.function = functionDefinition(name, identifier, isPublic, [False] * 32, None, None, None, dict(), None, dict(), dict(), list(), None, None, None)
        else:
            if self.function.isPublic is not None:
                duplicate = True
                self.function = functionDefinition(name, identifier, isPublic, [False] * 32, None, None, None, dict(), None, dict(), dict(), list(), None, None, None)
            else:
                self.function.isPublic = isPublic
                self.function.identifier = identifier
                thisData.definedFunctions.pop(name)
        thisData.usedIdentifierSlots.append(self.function)
        if duplicate:
            thisData.definedFunctions[f"{name}_{hex(identifier)[2:]}"] = self.function
        else:
            thisData.definedFunctions[name] = self.function
        thisData.functionTree.append(self.function)
        file.getNextTerm()
        assert file.term == '('
        file.allowGetNextLine(False, False)
        file.getNextTerm()
        self.arguments = list()
        delimiter = file.term
        if delimiter == ')':
            file.getNextTerm()
        else:
            while delimiter != ')':
                newArgument = expression()
                delimiter = newArgument.readFromCpp(file, thisData, ',)')
                assert len(newArgument.instructions) == 1
                newArgument = newArgument.instructions[0]
                self.arguments.append(newArgument)
                file.allowGetNextLine(False, False)
                file.getNextTerm()
        if file.term == '->':
            file.getNextTerm()
            self.function.specialLabel = file.term
            file.getNextTerm()
        assert file.term == '{'
        file.allowGetNextLine(False, False)
        thisData.getAccumulator()
    
    def writeToKsm(self, section: object):
        self.function.codeOffset = len(section.words)
        super().writeToKsm(section)
        section.words.append(self.function.identifier)
        for argument in self.arguments:
            argument.writeToKsm(section)
        closeFunctionArgumentsInstruction().writeToKsm(section)

#0x06
#OpenThread - The start of an anonymous thread (represented in c++ as a lambda function)
class openThreadInstruction(parentInstruction):
    name = "undefThread"
    specialLabelAlias = None
    
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        indentOffsetNextLine = 1
        
        argumentsTexts = [argument.writeToCpp(indentLevel)[0].removesuffix(';\n') for argument in self.arguments]
        
        capturesTexts = [argument.writeToCpp(indentLevel)[0].removesuffix(';\n') for argument in self.captures]
        
        summaryText = ', '.join(f"{capture} -> {argument}" for argument, capture in zip(argumentsTexts, capturesTexts))
        
        cppText = f"{'child' if isinstance(self, openThreadChildInstruction) else ''}thread {self.name}[{summaryText}] {'-> ' + self.specialLabelAlias if not self.specialLabelAlias is None else ''} {{\n"
        
        return cppText, indentLevel, indentOffsetNextLine
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        # function id - use to link to appropiate function definition
        getNextWord(wordsEnumerated, currentWord)
        
        linkedFunctionDefinition = functionDefinitionDictGet(currentWord.value)
        if not linkedFunctionDefinition is None:
            self.name = linkedFunctionDefinition.name[:-9]
        
        if not linkedFunctionDefinition.specialLabel is None:
            self.specialLabelAlias = linkedFunctionDefinition.specialLabel.alias
        
        global currentFunctionTree
        currentFunctionTree.append(linkedFunctionDefinition)
        
        self.arguments = []
        while True:
            getNextWord(wordsEnumerated, currentWord)
            newArgument = matchInstruction(currentWord.value)(currentWord.value, False)
            if isinstance(newArgument, closeFunctionArgumentsInstruction):
                break
            newArgument.readFromKsm(wordsEnumerated, currentWord)
            self.arguments.append(newArgument)
        
        # TODO: make this implementation not suck (this is to make the local variables focus on the parent function)
        rememberThreadFunction = currentFunctionTree[-1]
        currentFunctionTree.pop(-1)
        self.captures = []
        while True:
            getNextWord(wordsEnumerated, currentWord)
            newArgument = matchInstruction(currentWord.value)(currentWord.value, False)
            if isinstance(newArgument, closeCallArgumentsInstruction):
                break
            newArgument.readFromKsm(wordsEnumerated, currentWord)
            self.captures.append(newArgument)
        currentFunctionTree.append(rememberThreadFunction)
    
    def readFromCpp(self, file: object, thisData: object):
        thisData.bracesTree.append(self)
        thisData.declaredLabelStack.append(dict())
        assert file.term in ("thread", "childthread")
        file.getNextTerm()
        name = file.term
        identifier = len(thisData.usedIdentifierSlots) + thisData.identifierSlotOffset
        name = f"{name}_{hex(identifier | 0x3e000000)[2:]}"
        self.function = functionDefinition(name, identifier, False, [False] * 32, None, None, None, dict(), None, dict(), dict(), list(), None, None, None)
        thisData.definedFunctions[name] = self.function
        thisData.usedIdentifierSlots.append(self.function)
        file.getNextTerm()
        assert file.term == '['
        file.getNextTerm()
        self.captures = list()
        self.arguments = list()
        delimiter = file.term
        localVars = dict()
        if delimiter == ']':
            file.getNextTerm()
        else:
            while delimiter != ']':
                newCapture = expression()
                newCapture.readFromCpp(file, thisData, ('->',))
                assert len(newCapture.instructions) == 1
                newCapture = newCapture.instructions[0]
                file.allowGetNextLine(False, False)
                file.getNextTerm()
                newArgument = expression()
                thisData.localDefinedVariablesTree.append(localVars)
                thisData.functionTree.append(self.function)
                delimiter = newArgument.readFromCpp(file, thisData, ',]')
                file.allowGetNextLine(False, False)
                assert len(newArgument.instructions) == 1
                newArgument = newArgument.instructions[0]
                file.getNextTerm()
                self.captures.append(newCapture)
                self.arguments.append(newArgument)
                thisData.localDefinedVariablesTree.pop(-1)
                thisData.functionTree.pop(-1)
        thisData.localDefinedVariablesTree.append(localVars)
        thisData.localDefinedArraysTree.append(dict())
        thisData.localDefinedGlobalFlagsTree.append(dict())
        thisData.functionTree.append(self.function)
        if file.term == '->':
            file.getNextTerm()
            self.function.specialLabel = file.term
            file.getNextTerm()
        assert file.term == '{'
        file.allowGetNextLine(False, False)
    
    def writeToKsm(self, section: object):
        self.function.codeOffset = len(section.words)
        super().writeToKsm(section)
        section.words.append(self.function.identifier)
        for argument in self.arguments:
            argument.writeToKsm(section)
        closeFunctionArgumentsInstruction().writeToKsm(section)
        for capture in self.captures:
            capture.writeToKsm(section)
        closeCallArgumentsInstruction().writeToKsm(section)

#0x07
#OpenThreadChild - TODO: learn the difference
class openThreadChildInstruction(openThreadInstruction):
    pass

#0x08
#Close Function Arguments - The end of a function's arguments
class closeFunctionArgumentsInstruction(unknownInstruction):
    pass

#0x09
#Close Function - The end of a function
class closeFunctionInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        indentLevel -= 1
        return "}\n", indentLevel, 0
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        global currentFunctionTree
        currentFunctionTree.pop(-1)
    
    def readFromCpp(self, file: object, thisData: object):
        for thisLabel in thisData.declaredLabelStack[-1].values():
            if thisLabel.identifier is None:
                identifier = len(thisData.usedIdentifierSlots) + thisData.identifierSlotOffset
                thisLabel.identifier = identifier
                thisData.usedIdentifierSlots.append(thisLabel)
            thisData.functionTree[-1].labelsByID[thisLabel.identifier] = thisLabel
        
        self.pairedInstruction = thisData.bracesTree[-1]
        thisData.bracesTree.pop(-1)
        function = thisData.functionTree[-1]
        if function.accumulatorID is None:
            function.accumulator = thisData.getAccumulator()
            function.accumulatorID = function.accumulator.identifier
        thisData.functionTree.pop(-1)
        thisData.localDefinedVariablesTree.pop(-1)
        thisData.localDefinedArraysTree.pop(-1)
        thisData.localDefinedGlobalFlagsTree.pop(-1)
        thisData.declaredLabelStack.pop(-1)
        self.function = self.pairedInstruction.function
        file.allowGetNextLine(False, False)
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.function.codeEnd = len(section.words)
        

#0x0a
#Goto - Jump to a specified label in the function.
class gotoInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        isAltType = isinstance(self, caseGotoInstruction)
        return f"goto{'*' if isAltType else ''} {self.labelAlias};\n", indentLevel, 0
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        assert not self.disableExpression
        getNextWord(wordsEnumerated, currentWord)
        labelID = currentWord.value
        linkedLabelDefinition = currentFunctionTree[-1].labelsByID.get(labelID, None)
        self.labelAlias = linkedLabelDefinition.alias
    
    def readFromCpp(self, file: object, thisData: object):
        assert file.term == "goto"
        file.getNextTerm()
        name = file.term
        self.label = thisData.declaredLabelStack[-1].get(name, None)
        if self.label is None:
            self.label = label(None, None, name)
            thisData.declaredLabelStack[-1][name] = self.label
        file.allowGetNextLine(True, True)
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        section.words.append(self.label.identifier)

#0x0b
#Case Goto - Same as goto, but also safely exits the switch instruction that it's used in.
class caseGotoInstruction(gotoInstruction):
    pass

#0x0c
#Call - Used to execute another function within the current one.
class callInstruction(parentInstruction):
    isThreaded = False
    arguments = tuple()
    callee = unknownInstruction(0x00)
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        argumentsText = ", ".join(argument.writeToCpp(indentLevel)[0] for argument in self.arguments)
        if self.isThreaded:
            if self.isChild:
                threadText = 'childthread '
            else:
                threadText = 'thread '
        else:
            threadText = ''
        cppText = f"{threadText}{self.callee.writeToCpp(indentLevel)[0]}{'*' if self.disableExpression else ''}({argumentsText});\n"
        return cppText, indentLevel, 0
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        getNextWord(wordsEnumerated, currentWord)
        self.callee = matchInstruction(currentWord.value, True)(currentWord.value, False)
        self.arguments = []
        if self.disableExpression:
            while True:
                getNextWord(wordsEnumerated, currentWord)
                newArgument = matchInstruction(currentWord.value, True)(currentWord.value, False)
                if isinstance(newArgument, closeCallArgumentsInstruction):
                    break
                self.arguments.append(newArgument)
        else:
            while True:
                newArgument = expression()
                newArgument.readFromKsm(wordsEnumerated, currentWord)
                if not newArgument.instructions:
                    break
                self.arguments.append(newArgument)
    
    def readFromCpp(self, file: object, thisData: object, disableLineEnd: bool = False):
        name = file.term
        if (match:= thisData.definedImports.get(name, None)) is not None:
            if not match in thisData.usedImportSlots:
                thisData.usedImportSlots.append(match)
                match.identifier = len(thisData.usedImportSlots) + maxInstructionID
            match.timesUsed += 1
            thisData.importCount += 1
            self.match = match
        elif (match:= thisData.definedFunctions.get(name, None)) is not None:
            self.match = match
        else:
            self.match = functionDefinition(name, None, None, [False] * 32, None, None, None, dict(), None, dict(), dict(), list(), None, None, None)
            thisData.definedFunctions[name] = self.match
        file.getNextTerm()
        if file.term == '*':
            self.disableExpression = True
            thisData.allowDisableExpression = True
            file.getNextTerm()
        assert file.term == '('
        file.allowGetNextLine(False, False)
        file.getNextTerm()
        delimiter = file.term
        self.arguments = list()
        if delimiter == ')':
            file.getNextTerm()
        else:
            while delimiter != ')':
                newArgument = expression()
                file.allowGetNextLine(False, False)
                delimiter = newArgument.readFromCpp(file, thisData, ',)')
                if self.disableExpression:
                    assert len(newArgument.instructions) == 1, (file.index+1, newArgument.instructions)
                    newArgument = newArgument.instructions[0]
                self.arguments.append(newArgument)
                file.getNextTerm()
        if not disableLineEnd:
            file.allowGetNextLine(True, True)
        
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        section.words.append(self.match.identifier)
        for argument in self.arguments:
            argument.writeToKsm(section)
        closeCallArgumentsInstruction().writeToKsm(section)

#0x0d
#Thread Call - Execute another function in another thread.
class threadCallInstruction(callInstruction):
    isThreaded = True
    isChild = False
    
    def readFromCpp(self, file: object, thisData: object):
        assert file.term in ("thread", "childthread")
        file.getNextTerm()
        super().readFromCpp(file, thisData)

#0x0e
#Thread Call As Child - Execute another function in another thread (as a child of this thread?).
class threadCallChildInstruction(threadCallInstruction):
    isChild = True

...

#0x11
#Close Call Arguments - Used to end the list of arguments in a call instruction
class closeCallArgumentsInstruction(unknownInstruction):
    pass

#0x12
#Delete Variable - Mark a variable for deletion from memory.
class deleteVariableInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        if self.variable is None:
            return "delete;\n", indentLevel, 0
        return f"delete {self.variable.writeToCpp(indentLevel)[0]};\n", indentLevel, 0
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        assert not self.disableExpression
        getNextWord(wordsEnumerated, currentWord)
        self.variable = matchInstruction(currentWord.value)(currentWord.value, False)
        if isinstance(self.variable, closeExpressionInstruction):
            self.variable = None

    def readFromCpp(self, file: object, thisData: object):
        assert file.term == "delete"
        file.getNextTerm()
        self.variable = expression()
        self.variable.readFromCpp(file, thisData, ';')
        if len(self.variable.instructions) == 1:
            self.variable = self.variable.instructions[0]
        else:
            assert not self.variable.instructions
        file.allowGetNextLine(True, True)
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.variable.writeToKsm(section)

...

#0x15
#Is Child Thread Incomplete - Returns whether a given child thread is *not* done running.
class isChildThreadIncompleteInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        cppText = f"is_incomplete {self.variable.writeToCpp(indentLevel)[0]};\n"
        return cppText, indentLevel, 0
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        assert not self.disableExpression
        getNextWord(wordsEnumerated, currentWord)
        self.variable = matchInstruction(currentWord.value)(currentWord.value, False)
    
    def readFromCpp(self, file: object, thisData: object):
        assert file.term == "is_incomplete"
        file.getNextTerm()
        self.thread = expression()
        self.thread.readFromCpp(file, thisData, ';')
        assert len(self.thread.instructions) == 1
        self.thread = self.thread.instructions[0]
        file.allowGetNextLine(True, True)
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.thread.writeToKsm(section)

#0x16
#Sleep Frames - Pause the thread for n frames
class sleepFramesInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        cppText = f"sleep_frames{'*' if self.disableExpression else ''} {self.value.writeToCpp(indentLevel)[0]};\n"
        return cppText, indentLevel, 0
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        if self.disableExpression:
            getNextWord(wordsEnumerated, currentWord)
            self.value = matchInstruction(currentWord.value)(currentWord.value, False)
        else:
            self.value = expression()
        self.value.readFromKsm(wordsEnumerated, currentWord)
    
    def readFromCpp(self, file: object, thisData: object):
        assert file.term == "sleep_frames"
        file.getNextTerm()
        if file.term == '*':
            self.disableExpression = True
            thisData.allowDisableExpression = True
            file.getNextTerm()
        self.value = expression()
        self.value.readFromCpp(file, thisData, ';')
        if self.disableExpression:
            assert len(self.value.instructions) == 1
            self.value = self.value.instructions[0]
        file.allowGetNextLine(True, True)
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.value.writeToKsm(section)

#0x17
#Sleep Milliseconds - Pause the thread for n milliseconds
class sleepMillisecondsInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        cppText = f"sleep_milliseconds{'*' if self.disableExpression else ''} {self.value.writeToCpp(indentLevel)[0]};\n"
        return cppText, indentLevel, 0
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        if self.disableExpression:
            getNextWord(wordsEnumerated, currentWord)
            self.value = matchInstruction(currentWord.value)(currentWord.value, False)
        else:
            self.value = expression()
        self.value.readFromKsm(wordsEnumerated, currentWord)
    
    def readFromCpp(self, file: object, thisData: object):
        assert file.term == "sleep_milliseconds"
        file.getNextTerm()
        if file.term == '*':
            self.disableExpression = True
            thisData.allowDisableExpression = True
            file.getNextTerm()
        self.value = expression()
        self.value.readFromCpp(file, thisData, ';')
        if self.disableExpression:
            assert len(self.value.instructions) == 1
            self.value = self.value.instructions[0]
        file.allowGetNextLine(True, True)
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.value.writeToKsm(section)
#0x18
#If Statement - Run a branch of code only if an expression evaluates to be true ("true" just meaning not equal to 0).
class ifInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        indentOffsetNextLine = 1
        cppText = f"if{'*' if self.disableExpression else ''} {self.condition.writeToCpp(indentLevel)[0]} {{\n"
        return cppText, indentLevel, indentOffsetNextLine
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        if self.disableExpression:
            getNextWord(wordsEnumerated, currentWord)
            self.condition = matchInstruction(currentWord.value, True)(currentWord.value, False)
        else:
            self.condition = expression()
        self.condition.readFromKsm(wordsEnumerated, currentWord)
        # unused - discard
        getNextWord(wordsEnumerated, currentWord)
        # jump to offset - discard
        getNextWord(wordsEnumerated, currentWord)
        # also unused - discard
        getNextWord(wordsEnumerated, currentWord)
    
    def readFromCpp(self, file: object, thisData: object):
        thisData.bracesTree.append(self)
        assert file.term == "if"
        file.getNextTerm()
        self.condition = expression()
        self.condition.readFromCpp(file, thisData, '{')
        file.allowGetNextLine(False, False)
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.condition.writeToKsm(section)
        section.words.append(0)
        self.writeToAddress = len(section.words)
        section.words.append(0)
        section.words.append(0)
    
    def writeToKsmAfter(self, section: object):
        section.words[self.writeToAddress] = self.jumpOffset

#0x19
#If Equal - OBSOLETE, use "if" instead.
class ifEqualInstruction(parentInstruction):
    operator = "=="
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        indentOffsetNextLine = 1
        cppText = f"if {self.operator}({self.valueX.writeToCpp(indentLevel)[0]}, {self.valueY.writeToCpp(indentLevel)[0]}) {{\n"
        return cppText, indentLevel, indentOffsetNextLine
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        assert not self.disableExpression
        getNextWord(wordsEnumerated, currentWord)
        self.valueX = matchInstruction(currentWord.value, True)(currentWord.value, False)
        getNextWord(wordsEnumerated, currentWord)
        self.valueY = matchInstruction(currentWord.value, True)(currentWord.value, False)
        # jump to offset - discard
        getNextWord(wordsEnumerated, currentWord)
    
    def readFromCpp(self, file: object, thisData: object):
        assert file.term == "if"
        file.getNextTerm()
        assert file.term == self.operator
        file.getNextTerm()
        assert file.term == '('
        file.getNextTerm()
        self.valueX = expression()
        self.valueX.readFromCpp(file, thisData, ',')
        assert len(self.valueX.instructions) == 1
        self.valueX = self.valueX.instructions[0]
        file.getNextTerm()
        self.valueY = expression()
        self.valueY.readFromCpp(file, thisData, ')')
        assert len(self.valueY.instructions) == 1
        self.valueY = self.valueY.instructions[0]
        file.getNextTerm()
        assert file.term == '{'
        file.allowGetNextLine(False, False)
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.valueX.writeToKsm(section)
        self.valueY.writeToKsm(section)

#0x1a
#If Not Equal - OBSOLETE, use if instead.
class ifNotEqualInstruction(ifEqualInstruction):
    operator = "!="

#0x1b
#If Greater Than - OBSOLETE, use if instead.
class ifGreaterThanInstruction(ifEqualInstruction):
    operator = ">"

#0x1c
#If Less Than - OBSOLETE, use if instead.
class ifLessThanInstruction(ifEqualInstruction):
    operator = "<"

#0x1d
#If Less Than - OBSOLETE, use if instead.
class ifGreaterThanOrEqualInstruction(ifEqualInstruction):
    operator = ">="

#0x1e
#If Less Than - OBSOLETE, use if instead.
class ifLessThanOrEqualInstruction(ifEqualInstruction):
    operator = "<="

...

#0x26
#Else Statement
class elseInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        indentLevel -= 1
        indentOffsetNextLine = 1
        cppText = f"}} else {{\n"
        return cppText, indentLevel, indentOffsetNextLine
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        # jump to offset - discard
        getNextWord(wordsEnumerated, currentWord)
    
    def readFromCpp(self, file: object, thisData: object):
        self.pairedInstruction = thisData.bracesTree[-1] 
        thisData.bracesTree[-1] = self
        assert file.term == '}'
        file.getNextTerm()
        assert file.term == "else"
        file.getNextTerm()
        assert file.term == '{'
        file.allowGetNextLine(False, False)
    
    def writeToKsm(self, section: object):
        self.pairedInstruction.jumpOffset = len(section.words) + 2
        super().writeToKsm(section)
        self.writeToAddress = len(section.words)
        section.words.append(0)
    
    def writeToKsmAfter(self, section: object):
        section.words[self.writeToAddress] = self.jumpOffset

#0x27
#Else If Statement
class elseIfInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        indentLevel -= 1
        indentOffsetNextLine = 1
        cppText = f"}} else if{'*' if self.disableExpression else ''} {self.condition.writeToCpp(indentLevel)[0]} {{\n"
        return cppText, indentLevel, indentOffsetNextLine
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        # jump to offset - discard
        getNextWord(wordsEnumerated, currentWord)
        # unused - discard
        getNextWord(wordsEnumerated, currentWord)
        assert currentWord.value == 0x18, hex(currentWord.value)
        if self.disableExpression:
            getNextWord(wordsEnumerated, currentWord)
            self.condition = matchInstruction(currentWord.value, True)(currentWord.value, False)
        else:
            self.condition = expression()
            self.condition.readFromKsm(wordsEnumerated, currentWord)
        # also unused - discard
        getNextWord(wordsEnumerated, currentWord)
        # 2nd jump to offset - discard
        getNextWord(wordsEnumerated, currentWord)
        # also also unused - discard
        getNextWord(wordsEnumerated, currentWord)
    
    def readFromCpp(self, file: object, thisData: object):
        self.pairedInstruction = thisData.bracesTree[-1]
        thisData.bracesTree[-1] = self
        assert file.term == '}'
        file.getNextTerm()
        assert file.term == "else"
        file.getNextTerm()
        assert file.term == "if"
        file.getNextTerm()
        self.condition = expression()
        self.condition.readFromCpp(file, thisData, '{')
        file.allowGetNextLine(False, False)
        self.jumpOffset2 = None
    
    def writeToKsm(self, section: object):
        self.pairedInstruction.jumpOffset = len(section.words) + 2
        super().writeToKsm(section)
        self.writeToAddress = len(section.words)
        section.words.append(0)
        section.words.append(0x18)
        self.condition.writeToKsm(section)
        section.words.append(0)
        self.writeToAddress2 = len(section.words)
        section.words.append(0)
        section.words.append(0)
    
    def writeToKsmAfter(self, section: object):
        if self.jumpOffset2 is None:
            self.jumpOffset2 = self.jumpOffset
            self.jumpOffset -= 2
        section.words[self.writeToAddress] = self.jumpOffset
        section.words[self.writeToAddress2] = self.jumpOffset2
    
#0x28
#End If Statement - Close an If Statement branch
class endIfInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        indentLevel -= 1
        return "}\n", indentLevel, 0
    
    def readFromCpp(self, file: object, thisData: object):
        self.pairedInstruction = thisData.bracesTree[-1]
        thisData.bracesTree.pop(-1)
        assert file.term == '}'
        file.allowGetNextLine(False, False)
    
    def writeToKsm(self, section: object):
        if isinstance(self.pairedInstruction, elseInstruction):
            self.pairedInstruction.jumpOffset = len(section.words) + 1
        elif isinstance(self.pairedInstruction, elseIfInstruction):
            self.pairedInstruction.jumpOffset = len(section.words)
            self.pairedInstruction.jumpOffset2 = len(section.words)
        else:
            self.pairedInstruction.jumpOffset = len(section.words)
        super().writeToKsm(section)

#0x29
#Switch - Check what value a given value matches and jump to the according case.
#NOTE: Switch statements are NOT fall through in ksm, making BreakSwitch largely pointless!
class switchInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        indentOffsetNextLine = 2
        return f"switch {self.value.writeToCpp(indentLevel)[0]} {{\n", indentLevel, indentOffsetNextLine
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        assert not self.disableExpression
        getNextWord(wordsEnumerated, currentWord)
        self.value = matchInstruction(currentWord.value)(currentWord.value, False)
        if isinstance(self.value, closeExpressionInstruction):
            self.value = None
        #unused value - discard
        getNextWord(wordsEnumerated, currentWord)
        #jump offset - discard
        getNextWord(wordsEnumerated, currentWord)
    
    def readFromCpp(self, file: object, thisData: object):
        thisData.bracesTree.append(self)
        assert file.term == "switch"
        file.getNextTerm()
        self.value = expression()
        self.value.readFromCpp(file, thisData, '{')
        assert len(self.value.instructions) == 1
        self.value = self.value.instructions[0]
        file.allowGetNextLine(False, False)
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.value.writeToKsm(section)
        self.writeToAddress2 = len(section.words)
        section.words.append(0)
        self.writeToAddress = len(section.words)
        section.words.append(0)
    
    def writeToKsmAfter(self, section: object):
        section.words[self.writeToAddress] = self.jumpOffset
        section.words[self.writeToAddress2] = self.jumpOffset2

#0x2a
#Case - One potential place to jump to in a switch statement.
class caseInstruction(parentInstruction):
    operator = ""
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        indentLevel -= 1
        indentOffsetNextLine = 1
        return f"case {self.operator}{self.value.writeToCpp(indentLevel)[0]}:\n", indentLevel, indentOffsetNextLine
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        assert not self.disableExpression
        getNextWord(wordsEnumerated, currentWord)
        self.value = matchInstruction(currentWord.value, True)(currentWord.value, False)
        #jump offset - discard
        getNextWord(wordsEnumerated, currentWord)
    
    def readFromCpp(self, file: object, thisData: object):
        self.pairedInstruction = thisData.bracesTree[-1]
        if not isinstance(thisData.bracesTree[-1], switchInstruction):
            thisData.bracesTree.pop(-1)
        thisData.bracesTree.append(self)
        assert file.term == "case"
        file.getNextTerm()
        if self.operator:
            assert file.term == self.operator
            file.getNextTerm()
        self.value = expression()
        self.value.readFromCpp(file, thisData, ':')
        assert len(self.value.instructions) == 1
        self.value = self.value.instructions[0]
        file.allowGetNextLine(False, False)
    
    def writeToKsm(self, section: object):
        if self.pairedInstruction is not None:
            self.pairedInstruction.jumpOffset = len(section.words)
        super().writeToKsm(section)
        self.value.writeToKsm(section)
        self.writeToAddress = len(section.words)
        section.words.append(0)
    
    def writeToKsmAfter(self, section: object):
        section.words[self.writeToAddress] = self.jumpOffset

#0x2b
#Case Not Equal
class caseNotEqualInstruction(caseInstruction):
    operator = "!"

#0x2c
#Case Greater Than
class caseGreaterThanInstruction(caseInstruction):
    operator = ">"

#0x2d
#Case Less Than
class caseLessThanInstruction(caseInstruction):
    operator = "<"

#0x2e
#Case Greater Than Or Equal
class caseGreaterThanOrEqualInstruction(caseInstruction):
    operator = ">="

#0x2f
#Case Less Than Or Equal
class caseLessThanOrEqualInstruction(caseInstruction):
    operator = "<="

#0x30
#Case Range - Variant of case: Succeed if value falls within provided range.
class caseRangeInstruction(caseInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        indentLevel -= 1
        indentOffsetNextLine = 1
        return f"case {self.lowerBound.writeToCpp(indentLevel)[0]} ... {self.upperBound.writeToCpp(indentLevel)[0]}:\n", indentLevel, indentOffsetNextLine
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        assert not self.disableExpression
        getNextWord(wordsEnumerated, currentWord)
        self.lowerBound = matchInstruction(currentWord.value, True)(currentWord.value, False)
        getNextWord(wordsEnumerated, currentWord)
        self.upperBound = matchInstruction(currentWord.value, True)(currentWord.value, False)
        #jump offset - discard
        getNextWord(wordsEnumerated, currentWord)
    
    def readFromCpp(self, file: object, thisData: object):
        self.pairedInstruction = thisData.bracesTree[-1]
        thisData.bracesTree[-1] = self
        assert file.term == "case"
        file.getNextTerm()
        self.lowerBound = expression()
        self.lowerBound.readFromCpp(file, thisData, '...')
        assert len(self.lowerBound.instructions) == 1
        self.lowerBound = self.lowerBound.instructions[0]
        file.getNextTerm()
        self.upperBound = expression()
        self.upperBound.readFromCpp(file, thisData, ':')
        assert len(self.upperBound.instructions) == 1
        self.upperBound = self.upperBound.instructions[0]
        
        self.allowGetNextLine(False, False)
    
    def writeToKsm(self, section: object):
        if self.pairedInstruction is not None:
            self.pairedInstruction.jumpOffset = len(section.words)
        parentInstruction.writeToKsm(self, section)
        self.lowerBound.writeToKsm(section)
        self.upperBound.writeToKsm(section)
        self.writeToAddress = len(section.words)
        section.words.append(0)
    
    def writeToKsmAfter(self, section: object):
        section.words[self.writeToAddress] = self.jumpOffset
    
...

#0x36
#Case Default - Variant of case: Goes to this case if all other cases fail.
class caseDefaultInstruction(caseInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        indentLevel -= 1
        indentOffsetNextLine = 1
        return f"default:\n", indentLevel, indentOffsetNextLine
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        assert not self.disableExpression
        #unused - discard
        getNextWord(wordsEnumerated, currentWord)
        #jump offset - discard
        getNextWord(wordsEnumerated, currentWord)
    
    def readFromCpp(self, file: object, thisData: object):
        self.pairedInstruction = thisData.bracesTree[-1]
        thisData.bracesTree[-1] = self
        assert file.term == "default"
        file.getNextTerm()
        assert file.term == ':'
        file.allowGetNextLine(False, False)
    
    def writeToKsm(self, section: object):
        if self.pairedInstruction is not None:
            self.pairedInstruction.jumpOffset = len(section.words)
        parentInstruction.writeToKsm(self, section)
        section.words.append(0)
        self.writeToAddress = len(section.words)
        section.words.append(0)
    
    def writeToKsmAfter(self, section: object):
        section.words[self.writeToAddress] = self.jumpOffset

#0x37
#Break Switch - Jump to the end of the switch statement.
class breakSwitchInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        return "break;\n", indentLevel, 0
    
    def readFromCpp(self, file: object, thisData: object):
        assert file.term == "break"
        file.allowGetNextLine(True, True)

#0x38
#End Switch - Closes a switch statement.
class endSwitchInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        indentLevel -= 2
        return "}\n", indentLevel, 0    
    
    def readFromCpp(self, file: object, thisData: object):
        self.pairedInstruction = thisData.bracesTree[-1]
        thisData.bracesTree.pop(-1)
        if isinstance(thisData.bracesTree[-1], switchInstruction):
            self.pairedInstruction2 = thisData.bracesTree[-1]
            thisData.bracesTree.pop(-1)
        else:
            self.pairedInstruction2 = None
        assert file.term == '}'
        file.allowGetNextLine(False, False)
    
    def writeToKsm(self, section: object):
        if isinstance(self.pairedInstruction, switchInstruction):
            self.pairedInstruction.jumpOffset2 = len(section.words)
        else:
            self.pairedInstruction.jumpOffset = len(section.words)
        if self.pairedInstruction2 is not None:
            self.pairedInstruction2.jumpOffset2 = len(section.words)
        super().writeToKsm(section)

#0x39
#While Loop - Run a branch of code repeatedly until the expression evaluates to be false when about to start a loop.
class whileInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        indentOffsetNextLine = 1
        cppText = f"while{'*' if self.disableExpression else ''} {self.condition.writeToCpp(indentLevel)[0]} {{\n"
        return cppText, indentLevel, indentOffsetNextLine
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        if versionRaw >= 0x00010302:
            assert not self.disableExpression
            expressionBypass = True
        else:
            expressionBypass = False
        if self.disableExpression or expressionBypass:
            getNextWord(wordsEnumerated, currentWord)
            self.condition = matchInstruction(currentWord.value, True)(currentWord.value, False)
        else:
            self.condition = expression()
            self.condition.readFromKsm(wordsEnumerated, currentWord)
        # jump to offset - discard
        getNextWord(wordsEnumerated, currentWord)
    
    def readFromCpp(self, file: object, thisData: object):
        thisData.bracesTree.append(self)
        assert file.term == "while"
        file.getNextTerm()
        if file.term == '*':
            self.disableExpression = True
            thisData.allowDisableExpression = True
            file.getNextTerm()
        self.condition = expression()
        self.condition.readFromCpp(file, thisData, '{')
        if self.disableExpression:
            assert len(self.condition.instructions) == 1
            self.condition = self.condition.instructions[0]
        file.allowGetNextLine(False, False)
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.condition.writeToKsm(section)
        self.writeToAddress = len(section.words)
        section.words.append(0)
    
    def writeToKsmAfter(self, section: object):
        section.words[self.writeToAddress] = self.jumpOffset

#0x3a
#Break - Exit ("break") out of a while loop prematurely.
class breakWhileInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        return f"break;\n", indentLevel, 0
    
    def readFromCpp(self, file: object, thisData: object):
        assert file.term == "break"
        file.allowGetNextLine(True, True)

#0x3b
#Continue - Leave the current while loop iteration, and start a new one.
class continueWhileInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        return f"continue;\n", indentLevel, 0
    
    def readFromCpp(self, file: object, thisData: object):
        assert file.term == "continue"
        file.allowGetNextLine(True, True)

#0x3c
#End While - Closes a while loop.
class endWhileInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        indentLevel -= 1
        return "}\n", indentLevel, 0
        
    def readFromCpp(self, file: object, thisData: object):
        self.pairedInstruction = thisData.bracesTree[-1]
        thisData.bracesTree.pop(-1)
        assert file.term == '}'
        file.allowGetNextLine(False, False)
    
    def writeToKsm(self, section: object):
        self.pairedInstruction.jumpOffset = len(section.words)
        super().writeToKsm(section)

#0x3d
#Assignment - Set a variable to a value.
class assignmentInstruction(parentInstruction):
    assignee = None
    value = None
    isIncrement = False
    
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        indentOffsetNextLine = 0
        assigneeText, indentLevel, indentOffsetNextLine = self.assignee.writeToCpp(indentLevel)
        
        if self.value is None:
            cppText = f"{assigneeText}{'*' if self.disableExpression else ''};\n"
            return cppText, indentLevel, indentOffsetNextLine
        
        valueText, indentLevel, indentOffsetNextLine = self.value.writeToCpp(indentLevel)
        valueText = valueText.removesuffix(";\n")
        if self.isIncrement:
            cppText = f"{assigneeText}{'*' if self.disableExpression else ''}{valueText};\n"
        else:
            cppText = f"{assigneeText} {'*' if self.disableExpression else ''}= {valueText}{'' if valueText.endswith('{\n') else ';\n'}"
        return cppText, indentLevel, indentOffsetNextLine
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        def readNextReturnInstruction():
            nonlocal self
            getNextWord(wordsEnumerated, currentWord)
            returnInstructionID = currentWord.value & 0xff
            returnDisableExpression = bool(currentWord.value & 0x0100)
            self.value = matchInstruction(returnInstructionID)(returnInstructionID, returnDisableExpression)
            self.value.readFromKsm(wordsEnumerated, currentWord)
        
        getNextWord(wordsEnumerated, currentWord)
        self.assignee = matchInstruction(currentWord.value)(currentWord.value, False)
        if self.disableExpression:
            getNextWord(wordsEnumerated, currentWord)
            self.value = matchInstruction(currentWord.value, True)(currentWord.value, False)
            self.value.readFromKsm(wordsEnumerated, currentWord)
            if isinstance(self.value, closeExpressionInstruction):
                self.value = None
            elif isinstance(self.value, getNextFunctionReturnInstruction):
                readNextReturnInstruction()
            elif isinstance(self.value, operatorInstruction) and self.value.instructionID in (0x50, 0x51):
                self.isIncrement = True
        else:
            self.value = expression()
            self.value.readFromKsm(wordsEnumerated, currentWord)
            if len(self.value.instructions) == 0:
                self.value = None
            elif isinstance(self.value.instructions[0], getNextFunctionReturnInstruction):
                readNextReturnInstruction()
            elif isinstance(self.value.instructions[0], operatorInstruction) and self.value.instructions[0].instructionID in (0x50, 0x51):
                self.isIncrement = True
    
    def readFromCpp(self, file: object, thisData: object):
        self.gettingNext = False
        self.variable = expression()
        delimiter = self.variable.readFromCpp(file, thisData, ('=', ';', '*', '++', '--'))
        assert len(self.variable.instructions) == 1, (file.index+1, self.variable.instructions)
        self.variable = self.variable.instructions[0]
        if delimiter == '*':
            self.disableExpression = True
            thisData.allowDisableExpression = True
            file.getNextTerm()
            delimiter = file.term
        if delimiter != '=':
            self.value = expression()
            self.value.instructions = list()
            file.allowGetNextLine(True, True)
            return
            
        if not isinstance(match:= identifyInstructionFromCpp(file, thisData), (assignmentInstruction, type(None))):
            self.value = match
            self.gettingNext = True
            self.value.readFromCpp(file, thisData)
        else:
            self.value = expression()
            self.value.readFromCpp(file, thisData, ';')
            if self.disableExpression:
                assert len(self.value.instructions) == 1
                self.value = self.value.instructions[0]
            file.allowGetNextLine(True, True)
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.variable.writeToKsm(section)
        if self.gettingNext:
            getNextFunctionReturnInstruction().writeToKsm(section)
            if not self.disableExpression:
                closeExpressionInstruction().writeToKsm(section)
        self.value.writeToKsm(section)
    
    # def readFromCpp(self, file: object, thisData: object):
        # variableDefinition = file.readVariable()
        # variableDefinition = handleVariable(thisData, variableDefinition)
        # #print("pretest", variableDefinition, file.index+1)
        # instruction = generateVariableInstruction(thisData, variableDefinition)
        # thisData.instructionList.append(instruction)
        # if not file.allowGetNextLine(True, False):
            # file.getNextTerm()
            # #print("test", variableDefinition)
            # #print([hex(i.instructionID) for i in thisData.instructionList])
            # assert file.term == "=", f"Expected \"=\" but instead got \"{file.term}\" on line {file.index+1}"
            # file.getNextTerm()
            # if not readCallable(thisData) is None:
                # instruction = getNextFunctionReturnInstruction(None, False)
                # thisData.instructionList.append(instruction)
            # else:
                # instructions, _ = readExpression(thisData, ';')
                # thisData.instructionList.extend(instructions)
        # instruction = closeExpressionInstruction(None, False)
        # thisData.instructionList.append(instruction)
        # if not readCallable(thisData) is None:
            # pass

...

#0x3f
#Get Next Function Return Value - used by assignments to assign variables to the return value of a called function directly
class getNextFunctionReturnInstruction(unknownInstruction):
    pass

#0x40
#Close Expression
class closeExpressionInstruction(unknownInstruction):
    pass

#0x41 to 0x4f and 0x52 to 0x56
#Operators
class operatorInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        if versionRaw >= 0x00010302:
            return operatorDictAlt[self.instructionID], indentLevel, 0
            
        return operatorDict[self.instructionID], indentLevel, 0

...

#0x57
#Unidentified
class unidentified57Instruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        return f"unidentified_57({self.variable.writeToCpp(indentLevel)[0]}, {self.value.writeToCpp(indentLevel)[0]});\n", indentLevel, 0
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        assert not self.disableExpression
        getNextWord(wordsEnumerated, currentWord)
        self.variable = matchInstruction(currentWord.value, True)(currentWord.value, False)
        self.variable.readFromKsm(wordsEnumerated, currentWord)
        getNextWord(wordsEnumerated, currentWord)
        self.value = matchInstruction(currentWord.value, True)(currentWord.value, False)
        self.value.readFromKsm(wordsEnumerated, currentWord)
    
    def readFromCpp(self, file: object, thisData: object):
        assert file.term == "unidentified_57"
        file.getNextTerm()
        assert file.term == '('
        file.getNextTerm()
        
        self.variable = expression()
        self.variable.readFromCpp(file, thisData, ',')
        assert len(self.variable.instructions) == 1
        self.variable = self.variable.instructions[0]
        
        file.getNextTerm()
        
        self.value = expression()
        self.value.readFromCpp(file, thisData, ')')
        assert len(self.value.instructions) == 1
        self.value = self.value.instructions[0]
        
        file.allowGetNextLine(True, True)
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.variable.writeToKsm(section)
        self.value.writeToKsm(section)

...

#0x5b
#Unidentified - Modulo in place?
class unidentified5bInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        return f"unidentified_5b({self.variable.writeToCpp(indentLevel)[0]}, {self.value.writeToCpp(indentLevel)[0]});\n", indentLevel, 0
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        assert not self.disableExpression
        getNextWord(wordsEnumerated, currentWord)
        self.variable = matchInstruction(currentWord.value, True)(currentWord.value, False)
        self.variable.readFromKsm(wordsEnumerated, currentWord)
        getNextWord(wordsEnumerated, currentWord)
        self.value = matchInstruction(currentWord.value, True)(currentWord.value, False)
        self.value.readFromKsm(wordsEnumerated, currentWord)
    
    def readFromCpp(self, file: object, thisData: object):
        assert file.term == "unidentified_5b"
        file.getNextTerm()
        assert file.term == '('
        file.getNextTerm()
        
        self.variable = expression()
        self.variable.readFromCpp(file, thisData, ',')
        assert len(self.variable.instructions) == 1
        self.variable = self.variable.instructions[0]
        
        file.getNextTerm()
        
        self.value = expression()
        self.value.readFromCpp(file, thisData, ')')
        assert len(self.value.instructions) == 1
        self.value = self.value.instructions[0]
        
        file.allowGetNextLine(True, True)
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.variable.writeToKsm(section)
        self.value.writeToKsm(section)

...

#[parent]
#Array Open - marks the start of a array in the script (can be partway into a function in the case of local arrays)
class parentArrayOpenInstruction(parentInstruction):
    name = None
    length = 0
    dataTypeString = "unk"
    
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        if self.dataTypeString == "var_array":
            self.elements = [element.writeToCpp(indentLevel)[0] for element in self.elements]
        
        elementsString = ", ".join(self.elements)
        nameString = f"{self.dataTypeString} {self.name}"
        #lengthString = f"[{self.length}]" if self.dataTypeString != "var_array" else ""
        return f"{nameString} = {{{elementsString}}};\n", indentLevel, 0
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        def readArrayVariables() -> Generator[str]:
            nonlocal self, wordsEnumerated, currentWord
            for _ in range(self.length):
                getNextWord(wordsEnumerated, currentWord)
                yield matchInstruction(currentWord.value)(currentWord.value, False)
        
        def readArrayInts() -> Generator[str]:
            nonlocal self, wordsEnumerated, currentWord
            for _ in range(self.length):
                getNextWord(wordsEnumerated, currentWord)
                if currentWord.value >= 0x80000000:
                    yield repr(currentWord.value - 0x100000000)
                else:
                    yield repr(currentWord.value)
        
        def readArrayFloats() -> Generator[str]:
            nonlocal self, wordsEnumerated, currentWord
            for _ in range(self.length):
                getNextWord(wordsEnumerated, currentWord)
                value = unpack('<f', currentWord.value.to_bytes(4, byteorder='little'))[0]
                value = float('%.6g' % value) # round to 6 s.f.
                yield repr(value)
        
        def readArrayBools() -> Generator[str]:
            nonlocal self, wordsEnumerated, currentWord
            for _ in range(self.length // 4):
                getNextWord(wordsEnumerated, currentWord)
                for bitshift in range(4):
                    newVal = (currentWord.value >> (bitshift * 8)) & 0xff
                    assert newVal <= 1
                    yield "true" if newVal else "false"
            extraLength = self.length % 4
            if extraLength != 0:
                getNextWord(wordsEnumerated, currentWord)
                for bitshift in range(extraLength):
                    newVal = (currentWord.value >> (bitshift * 8)) & 0xff
                    assert newVal <= 1
                    yield "true" if newVal else "false"
                
        linkedArrayDefinition = arrayDefinitionDictByAddressGet(currentWord.index + 1, currentFunctionTree)
        if linkedArrayDefinition is None:
            raise Exception(f"Array {hex(currentWord.index + 1)} is not defined!!")
        self.name = linkedArrayDefinition.name
        self.length = linkedArrayDefinition.length
        
        self.elements = self.readArrayContents(wordsEnumerated, currentWord)
        # force exhaustion of generator (thanks, python)
        self.elements = list(self.elements)
        getNextWord(wordsEnumerated, currentWord)
        newInstruction = matchInstruction(currentWord.value)(currentWord.value, False)
        assert isinstance(newInstruction, arrayCloseInstruction), (hex(newInstruction.instructionID), hex(currentWord.index * 4))
    
    def readFromCpp(self, file: object, thisData: object):
        assert file.term == self.dataTypeString
        identifier = len(thisData.usedIdentifierSlots) + thisData.identifierSlotOffset
        file.getNextTerm()
        name = file.term
        self.array = arrayDefinition(name, None, identifier, None, None, self.dataType)
        thisData.usedIdentifierSlots.append(self.array)
        if not thisData.functionTree:
            thisData.definedGlobalArrays[name] = self.array
        else:
            thisData.functionTree[-1].localArraysByID[identifier] = self.array
            thisData.localDefinedArraysTree[-1][name] = self.array
        file.getNextTerm()
        assert file.term == '='
        file.getNextTerm()
        assert file.term == '{'
        self.array.values = list()
        if self.dataTypeString == "var_array":
            while True:
                file.getNextTerm()
                newValue = expression()
                delimiter = newValue.readFromCpp(file, thisData, ',}')
                assert len(newValue.instructions) == 1
                newValue = newValue.instructions[0]
                self.array.values.append(newValue)
                if delimiter == '}':
                    break
        else:
            while True:
                file.getNextTerm()
                self.array.values.append(file.readConstValue()[0])
                file.getNextTerm()
                if file.term == '}':
                    break
                assert file.term == ','
        self.array.length = len(self.array.values)
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.array.address = len(section.words)

#0x63
#Variable Array Open
class variableArrayOpenInstruction(parentArrayOpenInstruction):
    dataTypeString = "var_array"
    dataType = arrayDataType.Variable
    def readArrayContents(self, wordsEnumerated: enumerate[int], currentWord: object) -> Generator[str]:
        for _ in range(self.length):
            getNextWord(wordsEnumerated, currentWord)
            yield matchInstruction(currentWord.value)(currentWord.value, False)
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        for value in self.array.values:
            value.writeToKsm(section)
        arrayCloseInstruction().writeToKsm(section)

#0x64
#Int Array Open
class intArrayOpenInstruction(parentArrayOpenInstruction):
    dataTypeString = "int_array"
    dataType = arrayDataType.Int
    def readArrayContents(self, wordsEnumerated: enumerate[int], currentWord: object) -> Generator[str]:
        for _ in range(self.length):
            getNextWord(wordsEnumerated, currentWord)
            if currentWord.value >= 0x80000000:
                yield repr(currentWord.value - 0x100000000)
            else:
                yield repr(currentWord.value)
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        for value in self.array.values:
            section.words.append(value)
        arrayCloseInstruction().writeToKsm(section)

#0x65
#Float Array Open
class floatArrayOpenInstruction(parentArrayOpenInstruction):
    dataTypeString = "float_array"
    dataType = arrayDataType.Float
    def readArrayContents(self, wordsEnumerated: enumerate[int], currentWord: object) -> Generator[str]:
        for _ in range(self.length):
            getNextWord(wordsEnumerated, currentWord)
            value = unpack('<f', currentWord.value.to_bytes(4, byteorder='little'))[0]
            value = float('%.6g' % value) # round to 6 s.f.
            yield repr(value)
        
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        for value in self.array.values:
            section.words.frombytes(pack("f", value))
        arrayCloseInstruction().writeToKsm(section)

#0x66
#Array Close
class arrayCloseInstruction(parentInstruction):
    pass

#[parent]
#Parent Array Instruction
class parentArrayInstruction(parentInstruction):
    def readArrayFromCpp(self, file: object, thisData: object, delimiter: str | tuple[str]):
        name = file.term
        self.array = thisData.definedGlobalArrays.get(name, None)
        if self.array is None:
            self.array = thisData.localDefinedArraysTree[-1][name]
        file.getNextTerm()
        assert file.term in delimiter, (file.index+1, file.term, delimiter)
    
    def writeArrayToKsm(self, section: object):
        section.words.append(self.array.identifier)
    
    def readArrayReferenceFromCpp(self, file: object, thisData: object, delimiter: str | tuple[str]):
        self.array = expression()
        self.array.readFromCpp(file, thisData, delimiter)
        assert len(self.array.instructions) == 1
        self.array = self.array.instructions[0]
    
    def writeArrayReferenceToKsm(self, section: object):
        self.array.writeToKsm(section)

#0x67
#Get Array Length - returns length of a specified array.
class getArrayLengthInstruction(parentArrayInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        return f"length {self.array.writeToCpp(indentLevel)[0]};\n", indentLevel, 0
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        assert not self.disableExpression
        getNextWord(wordsEnumerated, currentWord)
        self.array = matchInstruction(currentWord.value)(currentWord.value, False)
    
    def readFromCpp(self, file: object, thisData: object):
        assert file.term == "length"
        file.getNextTerm()
        self.readArrayFromCpp(file, thisData, ';')
        file.allowGetNextLine(True, True)
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.writeArrayToKsm(section)

#0x68
#Read Array Entry
class readArrayEntryInstruction(parentArrayInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        return f"{self.array.writeToCpp(indentLevel)[0]}[{self.index.writeToCpp(indentLevel)[0]}];\n", indentLevel, 0
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        assert not self.disableExpression
        getNextWord(wordsEnumerated, currentWord)
        self.array = matchInstruction(currentWord.value)(currentWord.value, False)
        getNextWord(wordsEnumerated, currentWord)
        self.index = matchInstruction(currentWord.value)(currentWord.value, False)
    
    def readFromCpp(self, file: object, thisData: object):
        self.readArrayFromCpp(file, thisData, '[')
        file.getNextTerm()
        self.index = expression()
        self.index.readFromCpp(file, thisData, ']')
        assert len(self.index.instructions) == 1
        self.index = self.index.instructions[0]
        file.allowGetNextLine(True, True)
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.writeArrayToKsm(section)
        self.index.writeToKsm(section)

#0x69
#Copy 1 Array Entry - Functionally the same as Read Array Entry
class arrayCopy1Instruction(parentArrayInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        return f"array_copy_1({self.array.writeToCpp(indentLevel)[0]}, {self.index.writeToCpp(indentLevel)[0]}, {self.variable.writeToCpp(indentLevel)[0]});\n", indentLevel, 0
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        assert not self.disableExpression
        getNextWord(wordsEnumerated, currentWord)
        self.array = matchInstruction(currentWord.value)(currentWord.value, False)
        getNextWord(wordsEnumerated, currentWord)
        self.index = matchInstruction(currentWord.value, True)(currentWord.value, False)
        getNextWord(wordsEnumerated, currentWord)
        self.variable = matchInstruction(currentWord.value, True)(currentWord.value, False)
    
    def readFromCpp(self, file: object, thisData: object):
        assert file.term in ("array_copy_1", "array_assign_1")
        file.getNextTerm()
        assert file.term == '('
        file.getNextTerm()
        self.readArrayFromCpp(file, thisData, ',')
        file.getNextTerm()
        self.index = expression()
        self.index.readFromCpp(file, thisData, ',')
        assert len(self.index.instructions) == 1
        self.index = self.index.instructions[0]
        file.getNextTerm()
        self.variable = expression()
        self.variable.readFromCpp(file, thisData, ')')
        assert len(self.variable.instructions) == 1
        self.variable = self.variable.instructions[0]
        file.allowGetNextLine(True, True)
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.writeArrayToKsm(section)
        self.index.writeToKsm(section)
        self.variable.writeToKsm(section)

#0x6a
#Copy 2 Array Entries - same as the following:
#variableX = array[index];
#variableY = array[index + 1];
class arrayCopy2Instruction(parentArrayInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        return f"array_copy_2({self.array.writeToCpp(indentLevel)[0]}, {self.index.writeToCpp(indentLevel)[0]}, {self.variableX.writeToCpp(indentLevel)[0]}, {self.variableY.writeToCpp(indentLevel)[0]});\n", indentLevel, 0
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        assert not self.disableExpression
        getNextWord(wordsEnumerated, currentWord)
        self.array = matchInstruction(currentWord.value)(currentWord.value, False)
        getNextWord(wordsEnumerated, currentWord)
        self.index = matchInstruction(currentWord.value)(currentWord.value, False)
        getNextWord(wordsEnumerated, currentWord)
        self.variableX = matchInstruction(currentWord.value)(currentWord.value, False)
        getNextWord(wordsEnumerated, currentWord)
        self.variableY = matchInstruction(currentWord.value)(currentWord.value, False)
    
    def readFromCpp(self, file: object, thisData: object):
        assert file.term in ("array_copy_2", "array_assign_2")
        file.getNextTerm()
        assert file.term == '('
        file.getNextTerm()
        self.readArrayFromCpp(file, thisData, ',')
        file.getNextTerm()
        self.index = expression()
        self.index.readFromCpp(file, thisData, ',')
        assert len(self.index.instructions) == 1
        self.index = self.index.instructions[0]
        file.getNextTerm()
        self.variableX = expression()
        self.variableX.readFromCpp(file, thisData, ',')
        assert len(self.variableX.instructions) == 1
        self.variableX = self.variableX.instructions[0]
        file.getNextTerm()
        self.variableY = expression()
        self.variableY.readFromCpp(file, thisData, ')')
        assert len(self.variableY.instructions) == 1
        self.variableY = self.variableY.instructions[0]
        file.allowGetNextLine(True, True)
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.writeArrayToKsm(section)
        self.index.writeToKsm(section)
        self.variableX.writeToKsm(section)
        self.variableY.writeToKsm(section)

#0x6b
#Copy 3 Array Entries - same as the following:
#variableX = array[index];
#variableY = array[index + 1];
#variableZ = array[index + 2];
class arrayCopy3Instruction(parentArrayInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        return f"array_copy_3({self.array.writeToCpp(indentLevel)[0]}, {self.index.writeToCpp(indentLevel)[0]}, {self.variableX.writeToCpp(indentLevel)[0]}, {self.variableY.writeToCpp(indentLevel)[0]}, {self.variableZ.writeToCpp(indentLevel)[0]});\n", indentLevel, 0
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        assert not self.disableExpression
        getNextWord(wordsEnumerated, currentWord)
        self.array = matchInstruction(currentWord.value)(currentWord.value, False)
        getNextWord(wordsEnumerated, currentWord)
        self.index = matchInstruction(currentWord.value)(currentWord.value, False)
        getNextWord(wordsEnumerated, currentWord)
        self.variableX = matchInstruction(currentWord.value)(currentWord.value, False)
        getNextWord(wordsEnumerated, currentWord)
        self.variableY = matchInstruction(currentWord.value)(currentWord.value, False)
        getNextWord(wordsEnumerated, currentWord)
        self.variableZ = matchInstruction(currentWord.value)(currentWord.value, False)
    
    def readFromCpp(self, file: object, thisData: object):
        assert file.term in ("array_copy_3", "array_assign_3")
        file.getNextTerm()
        assert file.term == '('
        file.getNextTerm()
        self.readArrayFromCpp(file, thisData, ',')
        file.getNextTerm()
        self.index = expression()
        self.index.readFromCpp(file, thisData, ',')
        assert len(self.index.instructions) == 1
        self.index = self.index.instructions[0]
        file.getNextTerm()
        self.variableX = expression()
        self.variableX.readFromCpp(file, thisData, ',')
        assert len(self.variableX.instructions) == 1
        self.variableX = self.variableX.instructions[0]
        file.getNextTerm()
        self.variableY = expression()
        self.variableY.readFromCpp(file, thisData, ',')
        assert len(self.variableY.instructions) == 1
        self.variableY = self.variableY.instructions[0]
        file.getNextTerm()
        self.variableZ = expression()
        self.variableZ.readFromCpp(file, thisData, ')')
        assert len(self.variableZ.instructions) == 1
        self.variableZ = self.variableZ.instructions[0]
        file.allowGetNextLine(True, True)
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.writeArrayToKsm(section)
        self.index.writeToKsm(section)
        self.variableX.writeToKsm(section)
        self.variableY.writeToKsm(section)
        self.variableZ.writeToKsm(section)

#0x6c
#Array Assignment - assign a variable to an item of specific index in the array.
class arrayAssignmentInstruction(parentArrayInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        return f"{self.array.writeToCpp(indentLevel)[0]}[{self.index.writeToCpp(indentLevel)[0]}] = {self.variable.writeToCpp(indentLevel)[0]};\n", indentLevel, 0
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        assert not self.disableExpression
        getNextWord(wordsEnumerated, currentWord)
        self.array = matchInstruction(currentWord.value)(currentWord.value, False)
        getNextWord(wordsEnumerated, currentWord)
        self.index = matchInstruction(currentWord.value)(currentWord.value, False)
        getNextWord(wordsEnumerated, currentWord)
        self.variable = matchInstruction(currentWord.value)(currentWord.value, False)
    
    def readFromCpp(self, file: object, thisData: object):
        self.readArrayFromCpp(file, thisData, '[')
        self.index = expression()
        self.index.readFromCpp(file, thisData, ']')
        assert len(self.index.instructions) == 1
        self.index = self.index.instructions[0]
        file.getNextTerm()
        assert file.term == '='
        file.getNextTerm()
        self.variable = expression()
        self.variable.readFromCpp(file, thisData, ']')
        assert len(self.variable.instructions) == 1
        self.variable = self.variable.instructions[0]
        file.allowGetNextLine(True, True)
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.writeArrayToKsm(section)
        self.index.writeToKsm(section)
        self.variable.writeToKsm(section)

#0x6d
#Get Index - get the index where a value is found in an array
class arrayGetIndexInstruction(parentArrayInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        return f"index({self.array.writeToCpp(indentLevel)[0]}, {self.unknown.writeToCpp(indentLevel)[0]}, {self.variable.writeToCpp(indentLevel)[0]});\n", indentLevel, 0
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        assert not self.disableExpression
        getNextWord(wordsEnumerated, currentWord)
        self.array = matchInstruction(currentWord.value, True)(currentWord.value, False)
        self.array.readFromKsm(wordsEnumerated, currentWord)
        getNextWord(wordsEnumerated, currentWord)
        self.unknown = matchInstruction(currentWord.value)(currentWord.value, False)
        self.unknown.readFromKsm(wordsEnumerated, currentWord)
        getNextWord(wordsEnumerated, currentWord)
        self.variable = matchInstruction(currentWord.value)(currentWord.value, False)
        self.variable.readFromKsm(wordsEnumerated, currentWord)
    
    def readFromCpp(self, file: object, thisData: object):
        assert file.term == "index"
        file.getNextTerm()
        assert file.term == '('
        file.getNextTerm()
        self.readArrayFromCpp(file, thisData, ',')
        file.getNextTerm()
        self.unknown = expression()
        self.unknown.readFromCpp(file, thisData, ',')
        assert len(self.unknown.instructions) == 1
        self.unknown = self.unknown.instructions[0]
        file.getNextTerm()
        self.variable = expression()
        self.variable.readFromCpp(file, thisData, ')')
        assert len(self.variable.instructions) == 1
        self.variable = self.variable.instructions[0]
        file.allowGetNextLine(True, True)
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.writeArrayToKsm(section)
        self.unknown.writeToKsm(section)
        self.variable.writeToKsm(section)

#0x6e
#Global Code Open - for code outside any function in the script, not marked by anything in c++ scripts
class globalCodeOpenInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        indentOffsetNextLine = 1
        return '[\n', indentLevel, indentOffsetNextLine
#0x6f
#Global Code Close - for code outside any function in the script, not marked by anything in c++ scripts
class globalCodeCloseInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        indentLevel -= 1
        return ']\n', indentLevel, 0

...

#0x76
#Unidentified - set some unknown parameter
class unidentified76Instruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        return f"unidentified_76({self.variable.writeToCpp(indentLevel)[0]}, {self.value.writeToCpp(indentLevel)[0]});\n", indentLevel, 0
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        assert not self.disableExpression
        getNextWord(wordsEnumerated, currentWord)
        self.variable = matchInstruction(currentWord.value, True)(currentWord.value, False)
        self.variable.readFromKsm(wordsEnumerated, currentWord)
        self.value = readPotentialExpression(wordsEnumerated, currentWord, self.disableExpression)
    
    def readFromCpp(self, file: object, thisData: object):
        assert file.term == "unidentified_76"
        file.getNextTerm()
        assert file.term == '('
        file.getNextTerm()
        
        self.variable = expression()
        self.variable.readFromCpp(file, thisData, ',')
        assert len(self.variable.instructions) == 1
        self.variable = self.variable.instructions[0]
        file.getNextTerm()
        
        self.value = expression()
        self.value.readFromCpp(file, thisData, ')', True)
        
        file.allowGetNextLine(True, True)
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.variable.writeToKsm(section)
        self.value.writeToKsm(section)

#0x77
#Get Argument Count - Get the number of arguments that were entered into the function (all arguments are treated as optional in ksm, so this is how you check how many arguments have been set.)
class getArgumentCountInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        return "arg_count;\n", indentLevel, 0
    
    def readFromCpp(self, file: object, thisData: object):
        assert file.term == "arg_count"
        file.allowGetNextLine(True, True)

...

#0x7c
#Unidentified
class unidentified7cInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        return "unidentified_7c;\n", indentLevel, 0
    
    def readFromCpp(self, file: object, thisData: object):
        assert file.term == "unidentified_7c"
        file.allowGetNextLine(True, True)
    
#0x7d
#Unidentified
class unidentified7dInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        return "unidentified_7d;\n", indentLevel, 0
    
    def readFromCpp(self, file: object, thisData: object):
        assert file.term == "unidentified_7d"
        file.allowGetNextLine(True, True)
    
#0x7e
#Assignment (Function) - Set a variable to a callable function reference.
class functionAssignmentInstruction(assignmentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        indentOffsetNextLine = 0
        assigneeText, indentLevel, indentOffsetNextLine = self.assignee.writeToCpp(indentLevel)
        
        valueText, indentLevel, indentOffsetNextLine = self.value.writeToCpp(indentLevel)
        valueText = valueText.removesuffix(";\n")
        cppText = f"{assigneeText} {'*' if self.disableExpression else ''}= funcref {valueText}{'' if valueText.endswith('{\n') else ';\n'}"
        return cppText, indentLevel, indentOffsetNextLine
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        getNextWord(wordsEnumerated, currentWord)
        self.assignee = matchInstruction(currentWord.value)(currentWord.value, False)
        getNextWord(wordsEnumerated, currentWord)
        self.value = matchInstruction(currentWord.value)(currentWord.value, False)
    
    def readFromCpp(self, file: object, thisData: object):
        self.variable = expression()
        self.variable.readFromCpp(file, thisData, '=')
        assert len(self.variable.instructions) == 1
        self.variable = self.variable.instructions[0]
        file.getNextTerm()
        assert file.term == "funcref"
        file.getNextTerm()
        name = file.term
        if (match:= thisData.definedImports.get(name, None)) is not None:
            if not match in thisData.usedImportSlots:
                thisData.usedImportSlots.append(match)
                match.identifier = len(thisData.usedImportSlots) + maxInstructionID
            match.timesUsed += 1
            thisData.importCount += 1
            self.match = match
        elif (match:= thisData.definedFunctions.get(name, None)) is not None:
            self.match = match
        else:
            self.match = functionDefinition(name, None, None, [False] * 32, None, None, None, dict(), None, dict(), dict(), list(), None, None, None)
            thisData.definedFunctions[name] = self.match
        file.allowGetNextLine(True, True)
    
    def writeToKsm(self, section: object):
        parentInstruction.writeToKsm(self, section)
        self.variable.writeToKsm(section)
        section.words.append(self.match.identifier)

...

#0x80
#Variable Reference Call - Execute another function from a variable's reference to that function.
class variableCallInstruction(callInstruction):
    def readFromCpp(self, file: object, thisData: object, disableLineEnd: bool = False):
        self.variable = expression()
        self.variable.readFromCpp(file, thisData, '*(')
        assert len(self.variable.instructions) == 1
        self.variable = self.variable.instructions[0]
        file.getNextTerm()
        if file.term == '*':
            self.disableExpression = True
            thisData.allowDisableExpression = True
            file.getNextTerm()
        assert file.term == '('
        file.allowGetNextLine(False, False)
        file.getNextTerm()
        delimiter = file.term
        self.arguments = list()
        if delimiter == ')':
            file.getNextTerm()
        else:
            while delimiter != ')':
                newArgument = expression()
                file.allowGetNextLine(False, False)
                delimiter = newArgument.readFromCpp(file, thisData, ',)')
                if self.disableExpression:
                    assert len(newArgument.instructions) == 1, (file.index+1, newArgument.instructions)
                    newArgument = newArgument.instructions[0]
                self.arguments.append(newArgument)
                file.getNextTerm()
        if not disableLineEnd:
            file.allowGetNextLine(True, True)
    
    def writeToKsm(self, section: object):
        parentInstruction.writeToKsm(self, section)
        self.variable.writeToKsm(section)
        for argument in self.arguments:
            argument.writeToKsm(section)
        closeCallArgumentsInstruction().writeToKsm(section)

#0x81
#Variable Thread Call - Execute, from a variable's reference, a function in another thread.
class variableThreadCallInstruction(threadCallInstruction):
    def readFromCpp(self, file: object, thisData: object):
        assert file.term == "thread"
        file.getNextTerm()
        variableCallInstruction.readFromCpp(self, file, thisData)
    
    writeToKsm = variableCallInstruction.writeToKsm

#0x81
#Variable Thread Call As Child - Execute, from a variable's reference, another function in another thread (as a child of this thread?).
class variableThreadCallChildInstruction(threadCallChildInstruction): 
    def readFromCpp(self, file: object, thisData: object):
        assert file.term == "childthread"
        file.getNextTerm()
        variableCallInstruction.readFromCpp(self, file, thisData)
    
    writeToKsm = variableCallInstruction.writeToKsm
...

#0x85
#Cast to int - takes a value of another datatype, and returns that value as an integer
class castToIntegerInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        return f"int({self.value.writeToCpp(indentLevel)[0]});\n", indentLevel, 0
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        assert not self.disableExpression
        getNextWord(wordsEnumerated, currentWord)
        self.value = matchInstruction(currentWord.value)(currentWord.value, False)
    
    def readFromCpp(self, file: object, thisData: object):
        assert file.term == "int"
        file.getNextTerm()
        assert file.term == '('
        file.getNextTerm()
        self.value = expression()
        self.value.readFromCpp(file, thisData, ')')
        assert len(self.value.instructions) == 1
        self.value = self.value.instructions[0]
        file.allowGetNextLine(True, True)
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.value.writeToKsm(section)

#0x86
#Cast to float - takes a value of another datatype, and returns that value as an floating point value
class castToFloatingPointInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        return f"float({self.value.writeToCpp(indentLevel)[0]});\n", indentLevel, 0
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        assert not self.disableExpression
        getNextWord(wordsEnumerated, currentWord)
        self.value = matchInstruction(currentWord.value)(currentWord.value, False)
    
    def readFromCpp(self, file: object, thisData: object):
        assert file.term == "float"
        file.getNextTerm()
        assert file.term == '('
        file.getNextTerm()
        self.value = expression()
        self.value.readFromCpp(file, thisData, ')')
        assert len(self.value.instructions) == 1
        self.value = self.value.instructions[0]
        file.allowGetNextLine(True, True)
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.value.writeToKsm(section)

...


#0x89
#Sleep Until Complete - Sleep until referenced thread is done running.
class sleepUntilCompleteInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        cppText = f"sleep_until_complete{'*' if self.disableExpression else ''} {self.thread.writeToCpp(indentLevel)[0]};\n"
        return cppText, indentLevel, 0
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        self.thread = readPotentialExpression(wordsEnumerated, currentWord, self.disableExpression)
    
    def readFromCpp(self, file: object, thisData: object):
        assert file.term == "sleep_until_complete"
        file.getNextTerm()
        if file.term == '*':
            self.disableExpression = True
            thisData.allowDisableExpression = True
            file.getNextTerm()
        self.thread = expression()
        self.thread.readFromCpp(file, thisData, ';')
        if self.disableExpression:
            assert len(self.thread.instructions) == 1
            self.thread = self.thread.instructions[0]
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.thread.writeToKsm(section)

#0x8a
#Format String - use %s and %d as control characters in a string to be replaced with given substrings and digits, respectively.
class formatStringInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        argText = ", ".join(instruction.writeToCpp(indentLevel)[0] for instruction in self.arguments.instructions)
        cppText = f"format({self.assignee.writeToCpp(indentLevel)[0]}, {self.string.writeToCpp(indentLevel)[0]}, {argText});\n"
        return cppText, indentLevel, 0
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        assert not self.disableExpression
        getNextWord(wordsEnumerated, currentWord)
        self.assignee = matchInstruction(currentWord.value)(currentWord.value, False)
        getNextWord(wordsEnumerated, currentWord)
        self.string = matchInstruction(currentWord.value)(currentWord.value, False)
        self.arguments = readPotentialExpression(wordsEnumerated, currentWord, self.disableExpression)
    
    def readFromCpp(self, file: object, thisData: object):
        assert file.term == "format"
        file.getNextTerm()
        assert file.term == '('
        
        file.getNextTerm()
        self.variable = expression()
        self.variable.readFromCpp(file, thisData, ',')
        assert len(self.variable.instructions) == 1
        self.variable = self.variable.instructions[0]
        
        file.getNextTerm()
        self.string = expression()
        self.string.readFromCpp(file, thisData, ',)')
        assert len(self.string.instructions) == 1
        self.string = self.string.instructions[0]
        
        delimiter = file.term
        self.arguments = list()
        while delimiter != ')':
            file.getNextTerm()
            newArgument = expression()
            file.allowGetNextLine(False, False)
            delimiter = newArgument.readFromCpp(file, thisData, ',)')
            assert len(newArgument.instructions) == 1, (file.index+1, newArgument.instructions)
            newArgument = newArgument.instructions[0]
            self.arguments.append(newArgument)
        file.allowGetNextLine(True, True)
        
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.variable.writeToKsm(section)
        self.string.writeToKsm(section)
        for argument in self.arguments:
            argument.writeToKsm(section)
        closeExpressionInstruction().writeToKsm(section)

...

#0x8b
#Assign 1 Array Entries
class arrayAssign1Instruction(arrayCopy1Instruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        return f"array_assign_1({self.array.writeToCpp(indentLevel)[0]}, {self.index.writeToCpp(indentLevel)[0]}, {self.variable.writeToCpp(indentLevel)[0]});\n", indentLevel, 0


#0x8c
#Assign 2 Array Entries
class arrayAssign2Instruction(arrayCopy2Instruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        return f"array_assign_2({self.array.writeToCpp(indentLevel)[0]}, {self.index.writeToCpp(indentLevel)[0]}, {self.variableX.writeToCpp(indentLevel)[0]}, {self.variableY.writeToCpp(indentLevel)[0]});\n", indentLevel, 0


#0x8d
#Assign 3 Array Entries
class arrayAssign3Instruction(arrayCopy3Instruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        return f"array_assign_3({self.array.writeToCpp(indentLevel)[0]}, {self.index.writeToCpp(indentLevel)[0]}, {self.variableX.writeToCpp(indentLevel)[0]}, {self.variableY.writeToCpp(indentLevel)[0]}, {self.variableZ.writeToCpp(indentLevel)[0]});\n", indentLevel, 0

...

#0x8e
#Assignment (Array) - Set a variable to an array reference.
class assignmentReferenceArrayInstruction(parentArrayInstruction):
    assignee = None
    array = None
    
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        indentOffsetNextLine = 0
        assigneeText, indentLevel, indentOffsetNextLine = self.assignee.writeToCpp(indentLevel)
        
        valueText, indentLevel, indentOffsetNextLine = self.array.writeToCpp(indentLevel)
        cppText = f"{assigneeText} = {valueText};\n"
        return cppText, indentLevel, indentOffsetNextLine
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        assert not self.disableExpression
        getNextWord(wordsEnumerated, currentWord)
        self.assignee = matchInstruction(currentWord.value)(currentWord.value, False)
        getNextWord(wordsEnumerated, currentWord)
        self.array = matchInstruction(currentWord.value)(currentWord.value, False)
    
    def readFromCpp(self, file: object, thisData: object):
        self.variable = expression()
        self.variable.readFromCpp(file, thisData, '=')
        assert len(self.variable.instructions) == 1
        self.variable = self.variable.instructions[0]
        file.getNextTerm()
        self.readArrayFromCpp(file, thisData, ';')
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.variable.writeToKsm(section)
        self.writeArrayToKsm(section)

#0x8f
#Read Array Entry (variable referencing table)
class variableReferenceReadArrayEntryInstruction(readArrayEntryInstruction):
    def readArrayFromCpp(self, file: object, thisData: object, delimiter: str | tuple[str]):
        self.readArrayReferenceFromCpp(file, thisData, delimiter)
    
    def writeArrayToKsm(self, section: object):
        self.writeArrayReferenceToKsm(section)

#0x90
#Copy 1 Array Entry (variable referencing table)
class variableReferenceArrayCopy1Instruction(arrayCopy1Instruction):
    def readArrayFromCpp(self, file: object, thisData: object, delimiter: str | tuple[str]):
        self.readArrayReferenceFromCpp(file, thisData, delimiter)
    
    def writeArrayToKsm(self, section: object):
        self.writeArrayReferenceToKsm(section)

#0x91
#Copy 2 Array Entries (variable referencing table)
class variableReferenceArrayCopy2Instruction(arrayCopy2Instruction):
    def readArrayFromCpp(self, file: object, thisData: object, delimiter: str | tuple[str]):
        self.readArrayReferenceFromCpp(file, thisData, delimiter)
    
    def writeArrayToKsm(self, section: object):
        self.writeArrayReferenceToKsm(section)

#0x92
#Copy 3 Array Entries (variable referencing table)
class variableReferenceArrayCopy3Instruction(arrayCopy3Instruction):
    def readArrayFromCpp(self, file: object, thisData: object, delimiter: str | tuple[str]):
        self.readArrayReferenceFromCpp(file, thisData, delimiter)
    
    def writeArrayToKsm(self, section: object):
        self.writeArrayReferenceToKsm(section)

#0x93
#Array Assignment (variable referencing table)
class variableReferenceArrayAssignmentInstruction(arrayAssignmentInstruction):
    def readArrayFromCpp(self, file: object, thisData: object, delimiter: str | tuple[str]):
        self.readArrayReferenceFromCpp(file, thisData, delimiter)
    
    def writeArrayToKsm(self, section: object):
        self.writeArrayReferenceToKsm(section)

#0x94
#Array Get Index (variable referencing table)
class variableReferenceArrayGetIndexInstruction(arrayGetIndexInstruction):
    def readArrayFromCpp(self, file: object, thisData: object, delimiter: str | tuple[str]):
        self.readArrayReferenceFromCpp(file, thisData, delimiter)
    
    def writeArrayToKsm(self, section: object):
        self.writeArrayReferenceToKsm(section)

...

#0x98
#Boolean Array Open
class boolArrayOpenInstruction(parentArrayOpenInstruction):
    dataTypeString = "bool_array"
    dataType = arrayDataType.Bool
    def readArrayContents(self, wordsEnumerated: enumerate[int], currentWord: object) -> Generator[str]:
        for _ in range(self.length // 4):
            getNextWord(wordsEnumerated, currentWord)
            for bitshift in range(4):
                newVal = (currentWord.value >> (bitshift * 8)) & 0xff
                assert newVal <= 1
                yield "true" if newVal else "false"
        extraLength = self.length % 4
        if extraLength != 0:
            getNextWord(wordsEnumerated, currentWord)
            for bitshift in range(extraLength):
                newVal = (currentWord.value >> (bitshift * 8)) & 0xff
                assert newVal <= 1
                yield "true" if newVal else "false"
            
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        valuesModLength = len(self.array.values) % 4
        valuesPadLength = 4 - valuesModLength if valuesModLength != 0 else 0
        values = self.array.values + ([0] * valuesModLength)
        for i in range(0, len(values), 4):
            newVal = 0
            for bitshift in range(4):
                newVal |= values[i + bitshift] << (bitshift * 8)
            section.words.append(newVal)
        arrayCloseInstruction().writeToKsm(section)

...

#0x9c
#Get Array Length (variable referencing table)
class getVariableReferenceArrayLengthInstruction(getArrayLengthInstruction):
    def readArrayFromCpp(self, file: object, thisData: object, delimiter: str | tuple[str]):
        self.readArrayReferenceFromCpp(file, thisData, delimiter)
    
    def writeArrayToKsm(self, section: object):
        self.writeArrayReferenceToKsm(section)
    
#0x9d
#Get Data Type - returns as a string the datatype of the given value.
class getDataTypeInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        cppText = f"type {self.value.writeToCpp(indentLevel)[0]};\n"
        return cppText, indentLevel, 0
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        assert not self.disableExpression
        getNextWord(wordsEnumerated, currentWord)
        self.value = matchInstruction(currentWord.value)(currentWord.value, False)
    
    def readFromCpp(self, file: object, thisData: object):
        assert file.term == "type"
        file.getNextTerm()
        self.value = expression()
        self.value.readFromCpp(file, thisData, ';')
        assert len(self.value.instructions) == 1
        self.value = self.value.instructions[0]
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.value.writeToKsm(section)

...

#0x9e
#Sleep While - Sleep so long as the condition is true.
class sleepWhileInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        cppText = f"sleep_while {self.condition.writeToCpp(indentLevel)[0]};\n"
        return cppText, indentLevel, 0
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        #assert not self.disableExpression
        self.condition = expression()
        self.condition.readFromKsm(wordsEnumerated, currentWord)
        
        #unused - discard
        getNextWord(wordsEnumerated, currentWord)
        assert currentWord.value == 0x00000000
        getNextWord(wordsEnumerated, currentWord)
        assert currentWord.value == 0x00000000
    
    def readFromCpp(self, file: object, thisData: object):
        assert file.term == "sleep_while"
        file.getNextTerm()
        if file.term == '*':
            self.disableExpression = True
            thisData.allowDisableExpression = True
            file.getNextTerm()
        self.condition = expression()
        self.condition.readFromCpp(file, thisData, ';')
        if self.disableExpression:
            assert len(self.condition.instructions) == 1
            self.condition = self.condition.instructions[0]
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.condition.writeToKsm(section)
        section.words.append(0)
        section.words.append(0)

...

#0xa0
#Assert - Raise an error if a given value evaluates to be false (and print the format string after)
#NOTE: This instruction was before release. Executing this function just forcibily exits the function.
class assertInstruction(parentInstruction):
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        if not self.formatExpr.instructions:
            cppText = f"assert{'*' if self.disableExpression else ''}({self.condition.writeToCpp(indentLevel)[0]}, {self.message.writeToCpp.writeToCpp(indentLevel)[0]});\n"
        else:
            formatExprListText = ", ".join(instruction.writeToCpp(indentLevel)[0] for instruction in self.formatExpr.instructions)
            cppText = f"assert{'*' if self.disableExpression else ''}({self.condition.writeToCpp(indentLevel)[0]}, {self.message.writeToCpp(indentLevel)[0]}, {formatExprListText});\n"
        return cppText, indentLevel, 0
    
    def readFromKsm(self, wordsEnumerated: enumerate[int], currentWord: object):
        self.condition = readPotentialExpression(wordsEnumerated, currentWord, self.disableExpression)
        getNextWord(wordsEnumerated, currentWord)
        self.message = matchInstruction(currentWord.value)(currentWord.value, False)
        self.formatExpr = expression()
        self.formatExpr.readFromKsm(wordsEnumerated, currentWord)
    
    def readFromCpp(self, file: object, thisData: object):
        assert file.term == "assert"
        file.getNextTerm()
        if file.term == '*':
            self.disableExpression = True
            thisData.allowDisableExpression = True
            file.getNextTerm()
        assert file.term == '('
        file.getNextTerm()
        
        self.condition = expression()
        self.condition.readFromCpp(file, thisData, ',')
        if self.disableExpression:
            assert len(self.condition.instructions) == 1
            self.condition = self.condition.instructions[0]
        file.getNextTerm()
        
        self.message = expression()
        self.message.readFromCpp(file, thisData, ',)')
        assert len(self.message.instructions) == 1
        self.message = self.message.instructions[0]
        
        delimiter = file.term
        self.arguments = list()
        while delimiter != ')':
            file.getNextTerm()
            newArgument = expression()
            file.allowGetNextLine(False, False)
            delimiter = newArgument.readFromCpp(file, thisData, ',)')
            assert len(newArgument.instructions) == 1, (file.index+1, newArgument.instructions)
            newArgument = newArgument.instructions[0]
            self.arguments.append(newArgument)
            file.getNextTerm()
        file.allowGetNextLine(True, True)
    
    def writeToKsm(self, section: object):
        super().writeToKsm(section)
        self.condition.writeToKsm(section)
        self.message.writeToKsm(section)
        for argument in self.arguments:
            argument.writeToKsm(section)
        closeExpressionInstruction().writeToKsm(section)

#anything larger than 0x01ff is assumed to be a variable
class variableInstruction(parentInstruction):
    name = None
    alias = None
    scope = None
    isVariableDeclaration = False
    
    def __init__(self, instructionID: int | None = None, disableExpression: bool = False):
        parentInstruction.__init__(self, instructionID, disableExpression)
        if currentFunctionTree:
            variableDef = variableDictGet(self.instructionID, currentFunctionTree[-1])
        else:
            variableDef = variableDictGet(self.instructionID)
            
        self.isVariableDef = False
        if currentFunctionTree:
            self.function = currentFunctionTree[-1]
        else:
            self.function = None
        if variableDef is not None:
            self.isVariableDef = True
            self.name = variableDef.name
            self.alias = variableDef.alias
            self.scope = variableDef.scope
            self.value = variableDef.value
            self.dataTypeString = variableDef.dataTypeString
            if self.scope in (variableScope.tempVar, variableScope.localVar):
                if currentFunctionTree:
                    if self.scope == variableScope.tempVar:
                        if (baseID := (self.instructionID & 0xfffff0ff)) not in currentFunctionTree[-1].declaredLocals:
                            currentFunctionTree[-1].declaredLocals.add(baseID)
                            self.isVariableDeclaration = True
                        assert currentFunctionTree[-1].tempVarFlags[variableDef.identifier & 0xff]
                    elif self.instructionID not in currentFunctionTree[-1].declaredLocals:
                        currentFunctionTree[-1].declaredLocals.add(self.instructionID)
                        self.isVariableDeclaration = True
            
            elif variableDef.identifier not in variableIDsDefinedInCpp:
                variableIDsDefinedInCpp.add(variableDef.identifier)
                self.isVariableDeclaration = True
            
            if currentFunctionTree:
                if self.scope == variableScope.localVar and self.instructionID == currentFunctionTree[-1].accumulatorID:
                    self.name = "accumulator"
            return
        
        ArrayDef = arrayDefinitionDictByIDGet(self.instructionID, currentFunctionTree)
        if not ArrayDef is None:
            self.name = ArrayDef.name
        self.isConst = False
        
    
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        if self.scope == variableScope.const:
            return writeVariableValue(self.value, self.dataTypeString), indentLevel, 0
        
        prefixTxt = ""
        if self.isVariableDeclaration:
            scopeTxt = variableScopeEnumIntToStringDictGet(self.scope)
            prefixTxt = f"{scopeTxt} "
            if versionRaw < 0x00010302 and self.scope == variableScope.localVar and self.function.localVariableTypes[int(self.alias[8:])] == "ref":
                prefixTxt += "ref "
            if not self.scope in (variableScope.tempVar, variableScope.localVar, variableScope.tempStaticVar):
                prefixTxt += f"{self.dataTypeString} "
        elif self.isVariableDef and self.dataTypeString == "func" and self.function is not None and arrayDefinitionDictByNameGet(self.name, self.function) is None:
            prefixTxt += f"{self.dataTypeString} "
        
        if not self.name is None:
            return f"{prefixTxt}{self.name}", indentLevel, 0
        if not self.alias is None:
            return f"{prefixTxt}{self.alias}", indentLevel, 0
        
        return f"undef_{hex(self.instructionID)}", indentLevel, 0

class calledFunctionInstruction(parentInstruction):
    name = None
    def __init__(self, instructionID: int | None = None, disableExpression: bool = False):
        parentInstruction.__init__(self, instructionID, disableExpression)
        
        linkedFunctionDefinition = functionDefinitionDictGet(self.instructionID)
        if not linkedFunctionDefinition is None:
            self.name = linkedFunctionDefinition.name
        
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        if self.name is None:
            return f"{hex(self.instructionID)}", indentLevel, 0
        
        return self.name, indentLevel, 0
        
        return self.name, indentLevel, 0

class importedInstruction(parentInstruction):
    name = None
    def __init__(self, instructionID: int | None = None, disableExpression: bool = False):
        parentInstruction.__init__(self, instructionID, disableExpression)
        
        self.importDefinition = importDefinitionDictGet(self.instructionID)
        if self.importDefinition is None:
            self.name = "undef_" + hex(self.instructionID)
        else:
            self.name = self.importDefinition.name
    
    def writeToCpp(self, indentLevel: int) -> (str, int, int):
        if self.name is None:
            return f"{hex(self.instructionID)}", indentLevel, 0
        
        return self.name, indentLevel, 0

def matchInstruction(instructionID: int, biasForVariables: bool = True) -> parentInstruction:
    if not functionDefinitionDictGet(instructionID) is None:
        return calledFunctionInstruction
    
    if (instructionID & 0xffff0000):
        return variableInstruction
    
    if versionRaw >= 0x00010302:
        if 0x3e <= instructionID <= 0x53:
            checkForTargetInstruction(instructionID)
            return operatorInstruction
    elif 0x41 <= instructionID <= 0x56:
        checkForTargetInstruction(instructionID)
        return operatorInstruction
    
    if (instructionID & 0xff) > maxInstructionID or (biasForVariables and (instructionID & 0xff00)):
        return importedInstruction
    
    checkForTargetInstruction(instructionID)
    if versionRaw >= 0x00010302:
        return instructionDictAlt.get(instructionID, unknownInstruction)
    return instructionDict.get(instructionID, unknownInstruction)

def readPotentialExpression(wordsEnumerated: enumerate[int], currentWord: object, disableExpression: bool) -> parentInstruction | expression | None:
    if disableExpression:
        getNextWord(wordsEnumerated, currentWord)
        readVal = matchInstruction(currentWord.value, True)(currentWord.value, False)
        readVal.readFromKsm(wordsEnumerated, currentWord)
        if isinstance(readVal, closeExpressionInstruction):
            readVal = None
    else:
        readVal = expression()
        readVal.readFromKsm(wordsEnumerated, currentWord)
        if not readVal.instructions:
            readVal = None
    return readVal


instructionDict = {
    
    0x01: endFileInstruction,
    0x02: noopInstruction,
    0x03: returnInstruction,
    0x04: labelInstruction,
    0x05: openFunctionInstruction,
    0x06: openThreadInstruction,
    0x07: openThreadChildInstruction,
    0x08: closeFunctionArgumentsInstruction,
    0x09: closeFunctionInstruction,
    0x0a: gotoInstruction,
    0x0b: caseGotoInstruction,
    0x0c: callInstruction,
    0x0d: threadCallInstruction,
    0x0e: threadCallChildInstruction,
    #0x0f not found
    #0x10 not found
    0x11: closeCallArgumentsInstruction,
    0x12: deleteVariableInstruction,
    
    0x15: isChildThreadIncompleteInstruction,
    0x16: sleepFramesInstruction,
    0x17: sleepMillisecondsInstruction,
    0x18: ifInstruction,
    0x19: ifEqualInstruction,
    0x1a: ifNotEqualInstruction,
    0x1b: ifGreaterThanInstruction,
    0x1c: ifLessThanInstruction,
    0x1d: ifGreaterThanOrEqualInstruction,
    0x1e: ifLessThanOrEqualInstruction,
    #0x1f not found
    #0x20 not found
    #0x21 not found
    #0x22 not found
    #0x23 not found
    #0x24 not found
    #0x25 not found
    0x26: elseInstruction,
    0x27: elseIfInstruction,
    0x28: endIfInstruction,
    0x29: switchInstruction,
    0x2a: caseInstruction,
    0x2b: caseNotEqualInstruction,
    0x2c: caseGreaterThanInstruction,
    0x2d: caseLessThanInstruction,
    0x2e: caseGreaterThanOrEqualInstruction,
    0x2f: caseLessThanOrEqualInstruction,
    0x30: caseRangeInstruction,
    #0x31 not found
    #0x32 not found
    #0x33 not found
    #0x34 not found
    #0x35 not found
    0x36: caseDefaultInstruction,
    0x37: breakSwitchInstruction,
    0x38: endSwitchInstruction,
    0x39: whileInstruction,
    0x3a: breakWhileInstruction,
    0x3b: continueWhileInstruction,
    0x3c: endWhileInstruction,
    0x3d: assignmentInstruction,
    #0x3e not found
    0x3f: getNextFunctionReturnInstruction,
    0x40: closeExpressionInstruction,
    #...
    #operators are in this gap here
    #...
    0x57: unidentified57Instruction,
    
    0x5b: unidentified5bInstruction,
    #0x5c not found
    #0x5d not found
    
    #0x62 not found
    0x63: variableArrayOpenInstruction,
    0x64: intArrayOpenInstruction,
    0x65: floatArrayOpenInstruction,
    0x66: arrayCloseInstruction,
    0x67: getArrayLengthInstruction,
    0x68: readArrayEntryInstruction,
    0x69: arrayCopy1Instruction,
    0x6a: arrayCopy2Instruction,
    0x6b: arrayCopy3Instruction,
    0x6c: arrayAssignmentInstruction,
    0x6d: arrayGetIndexInstruction,
    0x6e: globalCodeOpenInstruction,
    0x6f: globalCodeCloseInstruction,
    #0x70 not found
    #0x71 not found
    #0x72 not found
    #0x73 not found
    #0x74 not found
    #0x75 not found
    0x76: unidentified76Instruction,
    0x77: getArgumentCountInstruction,
    #0x78 not found
    #0x79 not found
    #0x7a not found
    #0x7b not found
    0x7c: unidentified7cInstruction,
    0x7d: unidentified7dInstruction,
    0x7e: functionAssignmentInstruction,
    #0x7f not found
    0x80: variableCallInstruction,
    0x81: variableThreadCallInstruction,
    0x82: variableThreadCallChildInstruction,
    #0x83 not found
    #0x84 not found
    0x85: castToIntegerInstruction,
    0x86: castToFloatingPointInstruction,
    #0x87 not found
    #0x88 not found
    0x89: sleepUntilCompleteInstruction,
    0x8a: formatStringInstruction,
    0x8b: arrayAssign1Instruction,
    0x8c: arrayAssign2Instruction,
    0x8d: arrayAssign3Instruction,
    0x8e: assignmentReferenceArrayInstruction,
    0x8f: variableReferenceReadArrayEntryInstruction,
    0x90: variableReferenceArrayCopy1Instruction,
    0x91: variableReferenceArrayCopy2Instruction,
    0x92: variableReferenceArrayCopy3Instruction,
    0x93: variableReferenceArrayAssignmentInstruction,
    0x94: variableReferenceArrayGetIndexInstruction,
    #0x95 not found
    
    #0x97 not found
    0x98: boolArrayOpenInstruction,
    #0x99 not found
    #0x9a not found
    #0x9b not found
    0x9c: getVariableReferenceArrayLengthInstruction,
    0x9d: getDataTypeInstruction,
    #0x9e not found
    0x9f: sleepWhileInstruction,
    0xa0: assertInstruction,
}

#CAUTION: Because we're doing this, EVERY value in the dictionary above needs to be unique (use parenting to classes where necessary!)
invertedInstructionDict = {value: key for key, value in instructionDict.items()}

operatorDict = {
    0x41: '(',
    0x42: ')',
    
    0x43: '||',
    0x44: '&&',
    
    0x45: '|',
    0x46: '&',
    0x47: '^',
    0x48: '<<',
    0x49: '>>',
    
    0x4a: '==',
    0x4b: '!=',
    0x4c: '>',
    0x4d: '<',
    0x4e: '>=',
    0x4f: '<=',
    
    0x50: '++',
    0x51: '--',
    
    0x52: '%',
    0x53: '+',
    0x54: '-',
    0x55: '*',
    0x56: '/'
}

invertedOperatorDict = {value: key for key, value in operatorDict.items()}

instructionDictAlt = {
    
    0x01: endFileInstruction,
    0x02: noopInstruction,
    0x03: returnInstruction,
    0x04: labelInstruction,
    0x05: openFunctionInstruction,
    0x06: openThreadInstruction,
    0x07: openThreadChildInstruction,
    0x08: closeFunctionArgumentsInstruction,
    0x09: closeFunctionInstruction,
    0x0a: gotoInstruction,
    0x0b: callInstruction,
    0x0c: threadCallInstruction,
    0x0d: threadCallChildInstruction,
    
    0x10: closeCallArgumentsInstruction,
    0x11: deleteVariableInstruction,
    
    0x14: isChildThreadIncompleteInstruction,
    0x15: sleepFramesInstruction,
    0x16: sleepMillisecondsInstruction,
    0x17: ifInstruction,
    
    0x26: endIfInstruction,
    
    0x36: whileInstruction,    
    0x37: breakWhileInstruction,
    0x38: continueWhileInstruction,
    0x39: endWhileInstruction,
    0x3a: assignmentInstruction,
    
    0x3d: closeExpressionInstruction,
    
    0x6e: unidentified7cInstruction,
    0x6f: unidentified7dInstruction,
    
    0x72: variableCallInstruction,
    0x73: variableThreadCallInstruction,
    0x74: variableThreadCallChildInstruction,
    
}

operatorDictAlt = {
    0x3e: '(',
    0x3f: ')',
    
    0x40: '||',
    0x41: '&&',
    
    0x42: '|',
    0x43: '&',
    0x44: '^',
    0x45: '<<',
    0x46: '>>',
    
    0x47: '==',
    0x48: '!=',
    0x49: '>',
    0x4a: '<',
    0x4b: '>=',
    0x4c: '<=',
    
    0x4d: '++',
    0x4e: '--',
    
    0x4f: '%',
    0x50: '+',
    0x51: '-',
    0x52: '*',
    0x53: '/'
}



operatorChars = "".join(operatorDict.values()) + ";{}[]=,#\\:"
bracketsAndDelimiters = "(){}[],'\""

def isOperatorChar(character: str) -> bool:
    return character in operatorChars

def getOperatorIdentifier(operator: str) -> int | None:
    return invertedOperatorDict.get(operator, None)

def isBracketOrDelimiter(character: str) -> bool:
    return character in bracketsAndDelimiters

targetInstructionID = None
targetInstructionFound = None
foundInstructions = set()
def setTargetInstructionID(value: int | str):
    global targetInstructionID
    targetInstructionID = value
def getTargetInstructionFound() -> bool | set[int]:
    if not targetInstructionFound is None:
        return targetInstructionFound
    return foundInstructions
def setTargetInstructionFound(value: bool):
    global targetInstructionFound
    targetInstructionFound = value

def resetFoundInstructionsSet():
    global foundInstructions
    foundInstructions = set()

def checkForTargetInstruction(instructionID: int):
    global targetInstructionID, targetInstructionFound, foundInstructions
    assert 0x00 <= instructionID <= maxInstructionID
    if targetInstructionID == "all":
        foundInstructions.add(instructionID)
    elif not targetInstructionID is None and targetInstructionID == instructionID:
        targetInstructionFound = True

def setInstructionsVersionRaw(value: int):
    global versionRaw
    versionRaw = value

def identifyInstructionFromCpp(file: object, thisData: object, aligned: bool = False) -> parentInstruction | None:
    undirtyLine = file.line
    if aligned:
        undirtyTerm = file.term
        terms = [file.term] + [(file.getNextTerm(), file.term)[-1] for _ in range(4)]
    else:
        terms = [(file.getNextTerm(), file.term)[-1] for _ in range(5)]
    file.line = undirtyLine
    if aligned:
        file.term = undirtyTerm
    else:
        file.getNextTerm()
    
    if terms[0] == '"':
        return
    
    nameIsVar = lambda term: term in thisData.definedVariables or (thisData.localDefinedVariablesTree and term in thisData.localDefinedVariablesTree[-1])
    
    if terms[0] == "noop":
        return noopInstruction()
    if terms[0] == "return":
        return returnInstruction()
    if terms[0] in ("private", "public"):
        return openFunctionInstruction()
    if terms[2] == '[':
        if terms[0] == "thread":
            return openThreadInstruction()
        else:
            assert terms[0] == "childthread"
            return openThreadChildInstruction()
    if terms[0] == '}' and isinstance(thisData.bracesTree[-1], (openFunctionInstruction, openThreadInstruction)):
        return closeFunctionInstruction()
    if terms[0] == "goto":
        if any(True for instruction in thisData.bracesTree if isinstance(instruction, switchInstruction)):
            return caseGotoInstruction()
        else:
            return gotoInstruction()
    if terms[2] == '(' or terms[2] == '*' and terms[3] == '(':
        if terms[0] == "thread":
            if nameIsVar(terms[1]):
                return variableThreadCallInstruction()
            return threadCallInstruction()
        if terms[0] == "childthread":
            if nameIsVar(terms[1]):
                return variableThreadCallChildInstruction()
            return threadCallChildInstruction()
    if terms[0] == "delete":
        return deleteVariableInstruction()
    if terms[0] == "is_incomplete":
        return isChildThreadIncompleteInstruction()
    if terms[0] == "sleep_frames":
        return sleepFramesInstruction()
    if terms[0] == "sleep_milliseconds":
        return sleepMillisecondsInstruction()
    if terms[0] == "if":
        match terms[1]:
            case '==':
                return ifEqualInstruction()
            case '!=':
                return ifNotEqualInstruction()
            case '>':
                return ifGreaterThanInstruction()
            case '<':
                return ifLessThanInstruction()
            case '>=':
                return ifGreaterThanOrEqualInstruction()
            case '<=':
                return ifLessThanOrEqualInstruction()
            case _:
                return ifInstruction()
    if terms[0] == '}' and isinstance(thisData.bracesTree[-1], (ifInstruction, ifEqualInstruction, elseIfInstruction, elseInstruction)):
        if terms[1] == "else":
            if terms[2] == "if":
                return elseIfInstruction()
            else:
                return elseInstruction()
        else:
            return endIfInstruction()
    if terms[0] == "switch":
        return switchInstruction()
    if terms[0] == "case":
        match terms[1]:
            case '!=':
                return caseNotEqualInstruction()
            case '>':
                return caseGreaterThanInstruction()
            case '<':
                return caseLessThanInstruction()
            case '>=':
                return caseGreaterThanOrEqualInstruction()
            case '<=':
                return caseLessThanOrEqualInstruction()
            case _:
                if terms[2] == '...':
                    return caseRangeInstruction()
                else:
                    return caseInstruction()
    if terms[0] == "default":
        return caseDefaultInstruction()
    if terms[0] == "break":
        for instruction in thisData.bracesTree[::-1]:
            if isinstance(instruction, switchInstruction):
                breakType = switchInstruction
                break
            elif isinstance(instruction, whileInstruction):
                breakType = whileInstruction
                break
        else:
            breakType = None
        return breakSwitchInstruction() if breakType == switchInstruction else breakWhileInstruction()
    if terms[0] == '}' and isinstance(thisData.bracesTree[-1], (switchInstruction, caseInstruction)):
        return endSwitchInstruction()
    if terms[0] == "while":
        return whileInstruction()
    if terms[0] == "continue":
        return continueWhileInstruction()
    if terms[0] == '}' and isinstance(thisData.bracesTree[-1], whileInstruction):
        return endWhileInstruction()
    
    if terms[0] == "unidentified_57":
        return unidentified57Instruction()
    if terms[0] == "unidentified_5b":
        return unidentified5bInstruction()
    
    if terms[0] == "var_array":
        return variableArrayOpenInstruction()
    if terms[0] == "int_array":
        return intArrayOpenInstruction()
    if terms[0] == "float_array":
        return floatArrayOpenInstruction()
    if terms[0] == "bool_array":
        return boolArrayOpenInstruction()
    
    isArray = lambda term: term in thisData.definedGlobalArrays or term in thisData.localDefinedArraysTree[-1]
    
    if terms[0] == "length":
        return getArrayLengthInstruction() if isArray(terms[1]) else getVariableReferenceArrayLengthInstruction()
    if terms[1] == '[':
        if terms[terms.index(']') + 1] == '=':
            return arrayAssignmentInstruction() if isArray(terms[0]) else variableReferenceArrayAssignmentInstruction()
        return readArrayEntryInstruction() if isArray(terms[0]) else variableReferenceReadArrayEntryInstruction()
    
    if terms[0] == "array_copy_1":
        return arrayCopy1Instruction() if isArray(terms[2]) else variableReferenceArrayCopy1Instruction()
    if terms[0] == "array_copy_2":
        return arrayCopy2Instruction() if isArray(terms[2]) else variableReferenceArrayCopy2Instruction()
    if terms[0] == "array_copy_3":
        return arrayCopy3Instruction() if isArray(terms[2]) else variableReferenceArrayCopy3Instruction()
    if terms[0] == "index":
        return arrayGetIndexInstruction() if isArray(terms[2]) else variableReferenceArrayGetIndexInstruction()
    
    if terms[0] == "unidentified_76":
        return unidentified76Instruction()
    if terms[0] == "arg_count":
        return getArgumentCountInstruction()
    if terms[0] == "unidentified_7c":
        return unidentified7cInstruction()
    if terms[0] == "unidentified_7d":
        return unidentified7dInstruction()
    
    if terms[0] == '[':
        return globalCodeOpenInstruction()
    
    if terms[0] == ']':
        return globalCodeCloseInstruction()
    
    if terms[0] == "int" and terms[1] == '(':
        return castToIntegerInstruction()
    if terms[0] == "float" and terms[1] == '(':
        return castToFloatingPointInstruction()
    
    if terms[0] == "sleep_until_complete":
        return sleepUntilCompleteInstruction()
    if terms[0] == "format":
        return formatStringInstruction()
    
    if terms[0] == "array_assign_1":
        return arrayAssign1Instruction()
    if terms[0] == "array_assign_2":
        return arrayAssign2Instruction()
    if terms[0] == "array_assign_3":
        return arrayAssign3Instruction()
    
    if terms[0] == "type":
        return getDataTypeInstruction()
    if terms[0] == "sleep_while":
        return sleepWhileInstruction()
    if terms[0] == "assert":
        return assertInstruction()
    
    # keep this stuff at the bottom...
    if terms[1] == ':':
        return labelInstruction()
    
    if (terms[1] == '(' or (terms[1] == '*' and terms[2] == '(')) and not isOperatorChar(terms[0]):
        if nameIsVar(terms[0]):
            return variableCallInstruction()
        return callInstruction()
    
    if '=' in terms:
        valuePos = terms.index('=') + 1
        value = terms[valuePos]
        if value == "funcref":
            return functionAssignmentInstruction()
        if (value in thisData.definedGlobalArrays or (thisData.localDefinedArraysTree and value in thisData.localDefinedArraysTree[-1])) and terms[valuePos + 1] in (None, ';'):
            return assignmentReferenceArrayInstruction()
        else:
            return assignmentInstruction()
    
    return assignmentInstruction()
