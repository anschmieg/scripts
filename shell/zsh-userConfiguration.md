# Configuration of zsh shell according to my preferences

## Change to the directory of this file!

## Get Oh-my-zsh

### Install oh-my-zsh
sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"

### Install plugins
git clone https://github.com/zsh-users/zsh-autosuggestions $ZSH/custom/plugins/zsh-autosuggestions
git clone https://github.com/zsh-users/zsh-syntax-highlighting.git $ZSH/custom/plugins/zsh-syntax-highlighting

### Install bullet train theme - 
cd $ZSH_CUSTOM/themes/; curl -LJO http://raw.github.com/caiogondim/bullet-train-oh-my-zsh-theme/master/bullet-train.zsh-theme ; cd;

# Add _pure_ to path
# echo "" >> ~/.zshrc; echo fpath+=$(pwd)/pure >> ~/.zshrc
# echo "autoload -U promptinit; promptinit" >> ~/.zshrc; echo "prompt pure" >> ~/.zshrc
# source ~/.zshrc

