from dataclasses import dataclass
from collections import OrderedDict
from copy import copy
from gibberishModules.functionDefinitions import functionDefinition
from gibberishModules.terms import iterableFile
from gibberishModules.instructions import *
from gibberishModules.variables import variable, variableScope
from gibberishModules.imports import importDefinition
from gibberishModules.arrays import arrayDefinition

@dataclass
class compilationData:
    instructionList: list
    definedFunctions: OrderedDict[str, functionDefinition]
    usedIdentifierSlots: list[variable | functionDefinition | label]
    usedImportSlots: list
    localDefinedVariablesTree: list[dict[str, variable]]
    bracesTree: list[parentInstruction]
    functionTree: list[functionDefinition]
    constDict: dict
    importCount: int
    definedImports: dict[str, importDefinition]
    definedVariables: dict[str]
    identifierSlotOffset: int
    declaredLabelStack: list[dict[str, int]]
    allowDisableExpression: bool
    definedGlobalArrays: dict[str, arrayDefinition]
    localDefinedArraysTree: list[dict[str, arrayDefinition]]
    localDefinedGlobalFlagsTree : list[dict[str, variable]]
    
    def handleVariable(self, newVariable: variable, treeIndex: int = -1) -> variable:
        if (match := self.definedVariables.get(newVariable.name, None)) is not None:
            return match
        if (match := self.localDefinedVariablesTree[treeIndex].get(newVariable.name, None)) is not None:
            return match
        if newVariable.scope in (variableScope.localVar, variableScope.tempVar):
            if newVariable.dataTypeString is None:
                newVariable.dataTypeString = "int"
            newVariable = self.makeLocalVar(newVariable.name, newVariable.dataTypeString) if newVariable.scope == variableScope.localVar else self.makeTempVar(newVariable.name, newVariable.dataTypeString)
            return newVariable
        if (match := self.definedGlobalArrays.get(newVariable.name)) is not None or (self.localDefinedArraysTree and (match:= self.localDefinedArraysTree[-1].get(newVariable.name)) is not None):
            newVariable.dataTypeString = "func"
            newVariable.scope = variableScope.static
            return newVariable
        if newVariable.dataTypeString == "func":
            newVariable.scope = variableScope.static
            return newVariable
        raise Exception(f"Unknown variable \"{newVariable.name}\" of scope \"{newVariable.scope}\" on line {file.index+1}")

    def generateVariableInstruction(self, variableDefinition: variable) -> variableInstruction:
        jumpInToAddFlag = (variableDefinition.scope == variableScope.tempVar and variableDefinition.dataTypeString == "ref")
        if variableDefinition.dataTypeString == "globalflag" and (variableDefinition.name not in self.localDefinedGlobalFlagsTree[-1] or variableDefinition.name[:2] == "as"):
            if variableDefinition.name[:2] != "as":
                self.localDefinedGlobalFlagsTree[-1][variableDefinition.name] = variableDefinition
            if variableDefinition.identifier is not None:
                variableDefinition = copy(variableDefinition)
                variableDefinition.identifier = None
        
        if variableDefinition.identifier is None:
            variableID = len(self.usedIdentifierSlots) + self.identifierSlotOffset | 0x30000000
            self.usedIdentifierSlots.append(variableDefinition)
            variableDefinition.identifier = variableID
        instruction = variableInstruction(variableDefinition.identifier, False)
        if jumpInToAddFlag:
            instruction.instructionID = (instruction.instructionID & 0xfffff0ff) | 0x00000400
            variableDefinition.dataTypeString = "int"
        return instruction
    
    def getConst(self, value: int | float | str | bool | None, dataTypeString: str) -> variable:
        key = f"{dataTypeString}_{value}"
        if key in self.constDict:
            return self.constDict[key]
        identifier = len(self.usedIdentifierSlots) + self.identifierSlotOffset | 0x40000000
        alias = f"var_{hex(identifier)}"
        newConst = variable(None, identifier, alias, value, variableScope.const, dataTypeString)
        self.usedIdentifierSlots.append(newConst)
        self.constDict[key] = newConst
        return newConst
    
    def readAnyValue(self: object):
        if file.term == "accumulator":
            return self.getAccumulator()
        matchedOperator = getOperatorIdentifier(file.term)
        if not matchedOperator is None:
            return operatorInstruction(matchedOperator, False)
        
        matchedImport = self.definedImports.get(file.term, None)
        if not matchedImport is None:
            if not matchedImport in self.usedImportSlots:
                self.usedImportSlots.append(matchedImport)
                matchedImport.identifier = len(self.usedImportSlots) + 0xa0
            matchedImport.timesUsed += 1
            return importedInstruction(matchedImport.identifier, False)
        
        constValue, dataTypeString = file.readConstValue()
        if not constValue is None:
            return self.getConst(constValue, dataTypeString)
        
        matchedVariable = file.readVariable()
        return self.handleVariable(matchedVariable)
    
    def readExpression(self: object, exitingCharacters: str):# -> (list[parentInstruction], str):
        instructions = list()
        while True:
            if file.term in exitingCharacters:
                break
            if file.line == '' and ';' in exitingCharacters:
                break
            newValue = self.readAnyValue()
            match type(newValue).__name__:
                case "operatorInstruction":
                    newInstruction = newValue
                case "importedInstruction":
                    newInstruction = newValue
                case "variable":
                    newInstruction = variableInstruction(newValue.identifier, False)
            instructions.append(newInstruction)
            file.getNextTerm()
        return instructions, file.term
    
    def makeLocalVar(self, name: str, dataTypeString: str = "int") -> variable:
        identifier = (len(self.functionTree[-1].declaredLocals) << 8) | 0x20000000
        newLocal = variable(name, identifier, name, 0, variableScope.localVar, dataTypeString)
        self.functionTree[-1].declaredLocals.append(newLocal)
        self.localDefinedVariablesTree[-1][newLocal.name] = newLocal
        return newLocal    
    
    def makeTempVar(self: object, name: str, dataTypeString: str = "int") -> variable:
        tempCount = sum(self.functionTree[-1].tempVarFlags)
        identifier = tempCount | 0x10000100
        self.functionTree[-1].tempVarFlags[tempCount] = True
        newTemp = variable(name, identifier, name, 0, variableScope.tempVar, dataTypeString)
        self.localDefinedVariablesTree[-1][newTemp.name] = newTemp
        return newTemp
    
    def getAccumulator(self: object):
        accumulator = self.functionTree[-1].accumulator
        if accumulator is None:
            accumulator = self.makeLocalVar("accumulator")
            self.functionTree[-1].accumulator = accumulator
            self.functionTree[-1].accumulatorID = accumulator.identifier
        return accumulator
    
    def readCallable(self: object) -> functionDefinition | importDefinition | None:
        name = file.term
        matchedImport = self.definedImports.get(name, None)
        if not matchedImport is None and matchedImport.dataTypeString == "function":
            self.getAccumulator()
            self.importCount += 1
            matchedImport.timesUsed += 1
            if not matchedImport in self.usedImportSlots:
                self.usedImportSlots.append(matchedImport)
                matchedImport.identifier = len(self.usedImportSlots) + 0xa0
            return matchedImport
        
        matchedFunction = self.definedFunctions.get(name, None)
        if not matchedFunction is None:
            self.getAccumulator()
            return matchedFunction
        
        if file.line and file.line[0] == '(':
            self.getAccumulator()
            function = functionDefinition(name, None, None, None, None, None, None, None, None, None, None, None, None, None, None)
            self.definedFunctions[name] = function
            return function
        return None

def parseCppBodyFile(fileLines: list[str], definedImports: dict[str, importDefinition], definedVariables: dict, identifierSlotOffset: int):
    thisData = compilationData(list(), OrderedDict(), list(), list(), list(), list(), list(), dict(), 0, definedImports, definedVariables, identifierSlotOffset, list(), False, dict(), list(), list())
    global file
    file = iterableFile(fileLines)
    tobreak = False
    while True:
        file.allowGetNextLine(True, False)
        if file.line is None: break
        
        file.formatCurrentLine()
        
        while file.line == '' or file.line[0] == ';':
            file.allowGetNextLine(True, True)
            if file.line is None: 
                tobreak = True
                break
            file.formatCurrentLine()
        if tobreak:
            break
        
        newInstruction = identifyInstructionFromCpp(file, thisData)
        newInstruction.readFromCpp(file, thisData)
        thisData.instructionList.append(newInstruction)
    
    thisData.instructionList.append(endFileInstruction())
    
    return thisData.instructionList, thisData.definedFunctions, thisData.usedIdentifierSlots, thisData.usedImportSlots, thisData.importCount, thisData.allowDisableExpression